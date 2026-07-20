from pathlib import Path

from app.domain.models import DocumentCreate
from app.plugins.base import (
    DomainPlugin,
    PluginDocument,
    PluginKnowledgeBase,
    PluginTenant,
    WorkflowStepSpec,
)


INSURANCE_PLUGIN = DomainPlugin(
    plugin_id="insurance",
    name="保险知识库客服",
    version="1.0.0",
    workflow_version="insurance-v1",
    system_prompt=(
        "你是保险知识库客服 Agent。回答前必须调用知识库工具获取当前租户证据；"
        "不要编造保单条款、金额、承保结论或法律意见。证据不足时明确说明并建议转人工。"
    ),
    workflow=(
        WorkflowStepSpec(name="knowledge_retrieval", timeout_seconds=45),
        WorkflowStepSpec(name="safety_review", timeout_seconds=10),
    ),
    tool_names=("search_knowledge_base", "policy_lookup", "handoff_to_human"),
    policy_categories=frozenset({"policy", "product", "产品", "产品条款", "条款", "保障责任"}),
    tenants=(
        PluginTenant(
            tenant_id="demo",
            name="启明保险集团",
            plan="企业版",
            default_knowledge_base_id="insurance-general",
            settings={"display_name": "演示租户", "locale": "zh-CN"},
        ),
        PluginTenant(
            tenant_id="partner-a",
            name="安顺渠道合作方",
            plan="合作版",
            default_knowledge_base_id="partner-claims",
        ),
        PluginTenant(
            tenant_id="sandbox",
            name="产品测试租户",
            plan="沙箱",
            default_knowledge_base_id="sandbox-lab",
            enabled=False,
        ),
    ),
    knowledge_bases=(
        PluginKnowledgeBase(
            knowledge_base_id="insurance-general",
            tenant_id="demo",
            name="保险通用知识库",
            description="用于演示的保险产品、理赔和服务知识。",
        ),
        PluginKnowledgeBase(
            knowledge_base_id="motor-service",
            tenant_id="demo",
            name="车险服务知识库",
            description="车险报案、事故处理和查勘定损指引。",
            version=4,
        ),
        PluginKnowledgeBase(
            knowledge_base_id="health-products",
            tenant_id="demo",
            name="健康险产品知识库",
            description="医疗险、重疾险产品说明和服务规则。",
            version=7,
        ),
        PluginKnowledgeBase(
            knowledge_base_id="partner-claims",
            tenant_id="partner-a",
            name="合作渠道理赔库",
            description="合作渠道专属服务和理赔材料。",
            version=2,
            enabled=False,
        ),
        PluginKnowledgeBase(
            knowledge_base_id="sandbox-lab",
            tenant_id="sandbox",
            name="产品测试知识库",
            description="用于产品配置、提示词和检索策略验证。",
            enabled=False,
        ),
    ),
    documents=(
        PluginDocument(
            "insurance-general",
            DocumentCreate(
                document_id="demo-claim",
                title="理赔材料提交",
                content=(
                    "申请理赔通常需要提供保单信息、被保险人身份证明、事故证明和与损失相关的材料。"
                    "不同产品和事故类型的要求可能不同，请以保单约定和客服审核结果为准。"
                ),
                metadata={"category": "claims", "source": "demo"},
            ),
        ),
        PluginDocument(
            "motor-service",
            DocumentCreate(
                document_id="motor-claim",
                title="车险事故处理指引",
                content=(
                    "发生交通事故后，请先确保人员安全并按照当地要求报警。"
                    "报案和材料提交时效以产品条款与服务指引为准。"
                ),
                metadata={"category": "claims", "source": "demo"},
            ),
        ),
        PluginDocument(
            "health-products",
            DocumentCreate(
                document_id="health-reimburse",
                title="医疗费用报销范围",
                content="医疗费用报销范围需要结合产品责任、医院等级、免赔额以及条款约定综合判断。",
                metadata={"category": "policy", "source": "demo"},
            ),
        ),
        PluginDocument(
            "insurance-general",
            DocumentCreate(
                document_id="demo-cooling-off",
                title="犹豫期说明",
                content=(
                    "长期人身保险产品可能设置犹豫期。"
                    "犹豫期的具体天数、退保规则和费用处理以产品条款及投保单约定为准。"
                ),
                metadata={"category": "policy", "source": "demo"},
            ),
        ),
    ),
    evaluation_dataset=Path(__file__).resolve().parents[2] / "evals" / "dataset.jsonl",
)
