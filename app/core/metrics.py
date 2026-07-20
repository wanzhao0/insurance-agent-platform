from prometheus_client import Counter, Histogram


REQUESTS = Counter("agent_http_requests_total", "HTTP requests", ["method", "path", "status"])
REQUEST_DURATION = Histogram(
    "agent_http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)
CHAT_TURNS = Counter("agent_chat_turns_total", "Chat turns", ["tenant_id"])
TOOL_CALLS = Counter("agent_tool_calls_total", "Agent tool calls", ["tool_name"])
RAG_SEARCHES = Counter("agent_rag_searches_total", "RAG searches", ["result"])
RAG_DURATION = Histogram("agent_rag_search_duration_seconds", "RAG search latency")
WORKFLOW_STEPS = Counter(
    "agent_workflow_steps_total", "Workflow step executions", ["step", "status"]
)
WORKFLOW_STEP_DURATION = Histogram(
    "agent_workflow_step_duration_seconds",
    "Workflow step latency",
    ["step"],
)
TASKS = Counter("agent_tasks_total", "Background task outcomes", ["task_name", "status"])
