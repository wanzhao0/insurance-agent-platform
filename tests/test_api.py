import asyncio
import json
import os

os.environ.setdefault("AGENT_VECTOR_STORE_PROVIDER", "memory")
os.environ.setdefault("AGENT_PERSISTENCE_PROVIDER", "memory")

from fastapi.testclient import TestClient

from app.domain.models import DocumentCreate
from app.main import app


def test_health_and_public_config() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").json()["status"] == "ok"
        prototype = client.get("/prototype/")
        assert prototype.status_code == 200
        assert "保险 Agent 平台原型" in prototype.text
        assert client.get("/knowledge").status_code == 200
        assert client.get("/chat").status_code == 200
        config = client.get("/api/v1/config/public").json()
        assert config["model_provider"] == "mock"
        assert "model_api_key" not in config
        tenant = client.get("/api/v1/config/tenants/demo")
        assert tenant.status_code == 200
        assert tenant.json()["default_knowledge_base_id"] == "insurance-general"
        sandbox = client.get("/api/v1/config/tenants/sandbox")
        assert sandbox.status_code == 200
        assert sandbox.json()["default_knowledge_base_id"] == "sandbox-lab"


def test_rag_and_sse_chat() -> None:
    with TestClient(app) as client:
        search = client.post(
            "/api/v1/knowledge-bases/insurance-general/search",
            json={"query": "理赔材料"},
        )
        assert search.status_code == 200
        assert search.json()["results"]
        assert "lexical" in search.json()["results"][0]["retrieval_sources"]
        long_query = client.post(
            "/api/v1/knowledge-bases/insurance-general/search",
            json={"query": "请告诉我理赔需要准备什么材料"},
        )
        assert long_query.status_code == 200
        assert long_query.json()["results"]
        recommendation_search = client.post(
            "/api/v1/knowledge-bases/insurance-general/search",
            json={"query": "有什么保险产品可以推荐的"},
        )
        assert recommendation_search.status_code == 200
        assert recommendation_search.json()["results"] == []

        response = client.post(
            "/api/v1/chat/stream",
            json={"tenant_id": "demo", "messages": [{"role": "user", "content": "理赔材料"}]},
        )
        assert response.status_code == 200
        assert "event: token" in response.text
        assert "event: tool_call" in response.text
        assert "event: done" in response.text
        token_text = "".join(
            json.loads(line[5:])["content"]
            for line in response.text.splitlines()
            if line.startswith("data:") and json.loads(line[5:]).get("event") == "token"
        )
        assert "保单信息" in token_text
        assert "这是演示模式的客服回复" not in token_text

        recommendation_chat = client.post(
            "/api/v1/chat/stream",
            json={
                "tenant_id": "demo",
                "messages": [{"role": "user", "content": "有什么保险产品可以推荐的"}],
            },
        )
        recommendation_tokens = "".join(
            (json.loads(line[5:]).get("content") or "")
            for line in recommendation_chat.text.splitlines()
            if line.startswith("data:") and json.loads(line[5:]).get("event") == "token"
        )
        assert "没有检索到" in recommendation_tokens
        assert "犹豫期" not in recommendation_tokens


def test_admin_data_and_markdown_upload() -> None:
    with TestClient(app) as client:
        overview = client.get("/api/v1/admin/overview")
        assert overview.status_code == 200
        assert overview.json()["knowledge_base_count"] >= 4

        tenants = client.get("/api/v1/admin/tenants")
        assert tenants.status_code == 200
        assert any(item["tenant_id"] == "demo" for item in tenants.json())

        upload = client.post(
            "/api/v1/admin/documents/upload",
            data={"knowledge_base_id": "insurance-general", "category": "客服话术"},
            files={
                "file": (
                    "faq.md",
                    "# FAQ\n\n## 一、服务流程\n\n1. 客户提交报案。".encode("utf-8"),
                    "text/markdown",
                )
            },
        )
        assert upload.status_code == 201
        assert upload.json()["parser"] == "md"
        assert upload.json()["source_filename"] == "faq.md"
        assert upload.json()["status"] == "ready"
        assert upload.json()["source_uri"].startswith("local://")
        assert len(upload.json()["checksum"]) == 64
        assert upload.json()["index_version"]

        grounded_chat = client.post(
            "/api/v1/chat/stream",
            json={"tenant_id": "demo", "messages": [{"role": "user", "content": "服务流程"}]},
        )
        grounded_tokens = "".join(
            json.loads(line[5:])["content"]
            for line in grounded_chat.text.splitlines()
            if line.startswith("data:") and json.loads(line[5:]).get("event") == "token"
        )
        assert "客户提交报案" in grounded_tokens

        runtime = client.patch(
            "/api/v1/admin/runtime",
            json={"model_name": "insurance-agent-demo-v2", "rag_top_k": 5},
        )
        assert runtime.status_code == 200
        assert runtime.json()["model_name"] == "insurance-agent-demo-v2"
        assert runtime.json()["rag_top_k"] == 5

        evaluation = client.post("/api/v1/admin/evaluations/run", json={})
        assert evaluation.status_code == 200
        report = evaluation.json()
        assert report["dataset_size"] == 3
        assert report["grounded_answer_rate"] == 1.0
        assert report["no_context_precision"] == 1.0


def test_unsupported_upload_format_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/documents/upload",
            data={"knowledge_base_id": "insurance-general"},
            files={"file": ("legacy.doc", b"not a supported parser", "application/msword")},
        )
        assert response.status_code == 415


def test_auth_tools_metrics_and_public_boundaries() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "change-me"}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        assert token == "local-session"

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["role"] == "admin"

        tools = client.get("/api/v1/tools")
        assert tools.status_code == 200
        assert {item["name"] for item in tools.json()} == {
            "search_knowledge_base",
            "policy_lookup",
            "handoff_to_human",
        }

        metrics = client.get("/api/v1/metrics")
        assert metrics.status_code == 200
        assert "agent_http_requests_total" in metrics.text


def test_knowledge_routes_require_auth_outside_local_mode() -> None:
    with TestClient(app) as client:
        settings = app.state.container.settings
        previous_environment = settings.environment
        settings.environment = "production"
        try:
            search = client.post(
                "/api/v1/knowledge-bases/insurance-general/search",
                json={"query": "理赔材料"},
            )
            tenant = client.get("/api/v1/config/tenants/demo")
            assert search.status_code == 401
            assert tenant.status_code == 401
        finally:
            settings.environment = previous_environment


def test_reindex_removes_stale_document_chunks() -> None:
    with TestClient(app):
        container = app.state.container
        original = container.knowledge_base_service.add_document(
            "insurance-general",
            DocumentCreate(
                document_id="mutable-document",
                title="可更新文档",
                content="旧内容。" * 200,
            ),
        )
        asyncio.run(container.rag_service.index_document(original))
        assert any(
            key[1].startswith("mutable-document:chunk-")
            for key in container.vector_store._documents
        )

        updated = container.knowledge_base_service.add_document(
            "insurance-general",
            DocumentCreate(
                document_id="mutable-document",
                title="可更新文档",
                content="新内容。",
            ),
        )
        asyncio.run(container.rag_service.index_document(updated))
        assert ("insurance-general", "mutable-document") in container.vector_store._documents
        assert not any(
            key[1].startswith("mutable-document:chunk-")
            for key in container.vector_store._documents
        )


def test_repeated_seed_does_not_increment_document_versions() -> None:
    with TestClient(app):
        service = app.state.container.knowledge_base_service
        before = app.state.container.document_repository.get("insurance-general", "demo-claim")
        assert before is not None
        service.seed_defaults(app.state.container.domain_plugin)
        after = app.state.container.document_repository.get("insurance-general", "demo-claim")
        assert after is not None
        assert after.version == before.version


def test_user_rbac_and_token_revocation() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/admin/users",
            json={
                "username": "demo.viewer",
                "password": "viewer-password",
                "role": "viewer",
                "tenant_ids": ["demo"],
            },
        )
        assert created.status_code == 201
        user_id = created.json()["user_id"]

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "demo.viewer", "password": "viewer-password"},
        )
        token = login.json()["access_token"]
        assert token.startswith("local-")
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "viewer"
        assert client.get("/api/v1/config/tenants/demo", headers=headers).status_code == 200
        assert client.get("/api/v1/config/tenants/partner-a", headers=headers).status_code == 403
        assert client.get("/api/v1/admin/overview", headers=headers).status_code == 403

        disabled = client.patch(f"/api/v1/admin/users/{user_id}", json={"enabled": False})
        assert disabled.status_code == 200
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_config_rollback_workflow_history_and_governance() -> None:
    with TestClient(app) as client:
        plugins = client.get("/api/v1/admin/plugins")
        assert plugins.status_code == 200
        assert plugins.json()[0]["plugin_id"] == "insurance"

        first = client.patch(
            "/api/v1/admin/runtime",
            json={
                "model_name": "rollback-a",
                "rag_top_k": 3,
                "workflow_version": "insurance-test-v2",
                "system_prompt": "你是受知识库证据约束的保险客服，证据不足时必须明确拒绝给出具体结论。",
                "workflow_steps": [
                    {"name": "knowledge_retrieval", "timeout_seconds": 30, "on_error": "stop"},
                    {"name": "safety_review", "timeout_seconds": 10, "on_error": "stop"},
                ],
            },
        )
        assert first.status_code == 200
        first_version = first.json()["published_config_version"]
        assert first.json()["workflow_version"] == "insurance-test-v2"

        second = client.patch(
            "/api/v1/admin/runtime",
            json={"model_name": "rollback-b", "rag_top_k": 6},
        )
        assert second.status_code == 200
        assert second.json()["published_config_version"] > first_version

        versions = client.get("/api/v1/admin/config-versions").json()
        target = next(item for item in versions if item["version"] == first_version)
        assert target["values"]["model_name"] == "rollback-a"
        assert target["values"]["rag_top_k"] == 3
        rollback = client.post(f"/api/v1/admin/config-versions/{target['config_id']}/publish")
        assert rollback.status_code == 200
        runtime = client.get("/api/v1/admin/runtime").json()
        assert runtime["model_name"] == "rollback-a"
        assert runtime["rag_top_k"] == 3

        chat = client.post(
            "/api/v1/chat/stream",
            json={"tenant_id": "demo", "messages": [{"role": "user", "content": "理赔材料"}]},
        )
        assert chat.status_code == 200
        workflow_runs = client.get("/api/v1/admin/workflow-runs").json()
        assert workflow_runs[0]["workflow_version"] == "insurance-test-v2"
        assert [step["step"] for step in workflow_runs[0]["steps"]] == [
            "knowledge_retrieval",
            "safety_review",
        ]

        evaluation = client.post("/api/v1/admin/evaluations/run", json={})
        assert evaluation.status_code == 200
        evaluation_runs = client.get("/api/v1/admin/evaluations").json()
        assert evaluation_runs[0]["dataset_size"] == 3
        assert evaluation_runs[0]["workflow_version"] == "insurance-test-v2"

        container = app.state.container
        ticket = asyncio.run(
            container.tool_registry.invoke(
                "handoff_to_human",
                {
                    "tenant_id": "demo",
                    "conversation_id": "governance-test",
                    "reason": "需要核验保单原件",
                },
            )
        )
        handoffs = client.get("/api/v1/admin/handoffs").json()
        assert handoffs[0]["ticket_id"] == ticket.ticket_id
        closed = client.patch(
            f"/api/v1/admin/handoffs/{ticket.ticket_id}",
            json={"status": "closed"},
        )
        assert closed.json()["status"] == "closed"
        assert client.get("/api/v1/admin/audit-logs").json()
        assert client.get("/api/v1/admin/tasks").status_code == 200
