import json
import asyncio
from statistics import mean

from app.application.chat.service import ChatService
from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.service import RagService
from app.domain.models import (
    ChatMessage,
    ChatRequest,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationReport,
)
from app.plugins.base import DomainPlugin


class EvaluationService:
    def __init__(
        self,
        chat_service: ChatService,
        rag_service: RagService,
        knowledge_base_service: KnowledgeBaseService,
        model_client_provider,
        domain_plugin: DomainPlugin,
        evaluation_repository=None,
    ) -> None:
        self.chat_service = chat_service
        self.rag_service = rag_service
        self.knowledge_base_service = knowledge_base_service
        self.model_client_provider = model_client_provider
        self.domain_plugin = domain_plugin
        self.evaluation_repository = evaluation_repository

    def load_default_cases(self) -> list[EvaluationCase]:
        path = self.domain_plugin.evaluation_dataset
        return [
            EvaluationCase.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    async def run(self, cases: list[EvaluationCase], judge: str = "rules") -> EvaluationReport:
        results: list[EvaluationCaseResult] = []
        for case in cases:
            results.append(await self._run_case(case, judge))
        if not results:
            report = EvaluationReport(
                dataset_size=0,
                retrieval_hit_rate=0,
                citation_rate=0,
                grounded_answer_rate=0,
                no_context_precision=0,
                overall_score=0,
                cases=[],
            )
        else:
            no_context_cases = [
                result
                for result, case in zip(results, cases, strict=True)
                if case.expect_no_context
            ]
            citation_cases = [
                result
                for result, case in zip(results, cases, strict=True)
                if not case.expect_no_context
            ]
            report = EvaluationReport(
                dataset_size=len(results),
                retrieval_hit_rate=round(mean(result.retrieval_hit for result in results), 4),
                citation_rate=round(mean(result.citation_present for result in citation_cases), 4)
                if citation_cases
                else 1.0,
                grounded_answer_rate=round(mean(result.grounded for result in results), 4),
                no_context_precision=round(
                    mean(result.no_context_safe for result in no_context_cases), 4
                )
                if no_context_cases
                else 1.0,
                overall_score=round(mean(result.judge_score for result in results), 4),
                cases=results,
            )
        if self.evaluation_repository is not None:
            model_client = self.model_client_provider()
            model_name = (
                getattr(model_client, "model_name", None) or self.chat_service.settings.model_name
            )
            await asyncio.to_thread(
                self.evaluation_repository.save,
                report,
                judge,
                model_name,
                self.domain_plugin.plugin_id,
                self.domain_plugin.workflow_version,
            )
        return report

    async def _run_case(self, case: EvaluationCase, judge: str) -> EvaluationCaseResult:
        knowledge_base_id = await asyncio.to_thread(
            self.knowledge_base_service.resolve_knowledge_base,
            case.tenant_id,
            case.knowledge_base_id,
        )
        retrieved = await self.rag_service.search(knowledge_base_id, case.query)
        context = await asyncio.to_thread(
            self.chat_service.prepare,
            ChatRequest(
                tenant_id=case.tenant_id,
                knowledge_base_id=knowledge_base_id,
                messages=[ChatMessage(role="user", content=case.query)],
            ),
            persist_conversation=False,
        )
        answer_parts: list[str] = []
        citations = []
        async for event in self.chat_service.stream(context):
            if event.event == "token" and event.content:
                answer_parts.append(event.content)
            if event.event == "citation" and event.citation:
                citations.append(event.citation)
        answer = "".join(answer_parts)
        retrieved_ids = [item.document_id for item in retrieved]
        retrieval_hit = (
            not retrieved
            if case.expect_no_context
            else any(document_id in retrieved_ids for document_id in case.expected_document_ids)
        )
        grounded = all(phrase in answer for phrase in case.expected_phrases) and not any(
            phrase in answer for phrase in case.forbidden_phrases
        )
        no_context_safe = not case.expect_no_context or (
            not retrieved
            and "没有检索到" in answer
            and not any(phrase in answer for phrase in case.forbidden_phrases)
        )
        citation_present = bool(citations)
        rule_score = mean(
            [
                float(retrieval_hit),
                float(grounded),
                float(no_context_safe),
                float(citation_present or case.expect_no_context),
            ]
        )
        judge_score, judge_reason = rule_score, "规则评测"
        if judge == "llm":
            judge_score, judge_reason = await self._llm_judge(
                case, answer, retrieved, rule_score, grounded, no_context_safe
            )
        return EvaluationCaseResult(
            case_id=case.case_id,
            query=case.query,
            retrieved_document_ids=retrieved_ids,
            answer=answer,
            retrieval_hit=retrieval_hit,
            citation_present=citation_present,
            grounded=grounded,
            no_context_safe=no_context_safe,
            judge_score=round(judge_score, 4),
            judge_reason=judge_reason,
        )

    async def _llm_judge(self, case, answer, retrieved, fallback_score, grounded, no_context_safe):
        prompt = {
            "query": case.query,
            "evidence": [item.model_dump(mode="json") for item in retrieved],
            "answer": answer,
            "expected_phrases": case.expected_phrases,
            "forbidden_phrases": case.forbidden_phrases,
        }
        messages = [
            ChatMessage(
                role="system",
                content='你是客服 Agent 质量评测裁判。只返回 JSON：{"score":0到1之间的小数,"reason":"简短理由"}。'
                "判断回答是否基于证据、是否满足问题和安全边界。",
            ),
            ChatMessage(role="user", content=json.dumps(prompt, ensure_ascii=False)),
        ]
        try:
            completion = await self.model_client_provider().complete(messages)
            payload = json.loads(completion.content or "")
            score = max(0.0, min(1.0, float(payload["score"])))
            return score, str(payload.get("reason", "LLM 评测"))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return fallback_score, "LLM 评测结果不可解析，回退规则评测"
