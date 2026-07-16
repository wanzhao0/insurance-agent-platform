import json
import os

os.environ.setdefault("AGENT_VECTOR_STORE_PROVIDER", "memory")
os.environ.setdefault("AGENT_PERSISTENCE_PROVIDER", "memory")

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_public_config() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").json()["status"] == "ok"
        prototype = client.get("/prototype/")
        assert prototype.status_code == 200
        assert "保险 Agent 平台原型" in prototype.text
        config = client.get("/api/v1/config/public").json()
        assert config["model_provider"] == "mock"
        assert "model_api_key" not in config
        tenant = client.get("/api/v1/config/tenants/demo")
        assert tenant.status_code == 200
        assert tenant.json()["default_knowledge_base_id"] == "insurance-general"


def test_rag_and_sse_chat() -> None:
    with TestClient(app) as client:
        search = client.post(
            "/api/v1/knowledge-bases/insurance-general/search",
            json={"query": "理赔材料"},
        )
        assert search.status_code == 200
        assert search.json()["results"]
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
            json={"tenant_id": "demo", "messages": [{"role": "user", "content": "有什么保险产品可以推荐的"}]},
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
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "change-me"})
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
