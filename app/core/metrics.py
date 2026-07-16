from prometheus_client import Counter, Histogram


REQUESTS = Counter("agent_http_requests_total", "HTTP requests", ["method", "path", "status"])
REQUEST_DURATION = Histogram("agent_http_request_duration_seconds", "HTTP request latency", ["method", "path"])
CHAT_TURNS = Counter("agent_chat_turns_total", "Chat turns", ["tenant_id"])
TOOL_CALLS = Counter("agent_tool_calls_total", "Agent tool calls", ["tool_name"])
