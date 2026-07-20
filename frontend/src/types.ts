export type Role = 'system' | 'user' | 'assistant' | 'tool'

export interface UserContext {
  user_id: string
  username: string
  role: 'admin' | 'operator' | 'viewer'
  tenant_ids: string[]
}

export interface User extends UserContext {
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface Tenant {
  tenant_id: string
  name: string
  plan: string
  default_knowledge_base_id: string
  knowledge_base_count: number
  version: number
  enabled: boolean
}

export interface KnowledgeBase {
  knowledge_base_id: string
  tenant_id: string
  name: string
  description: string
  version: number
  document_count: number
  enabled: boolean
}

export interface Document {
  document_id: string
  knowledge_base_id: string
  title: string
  content: string
  metadata: Record<string, unknown>
  version: number
  created_at: string
  status: 'uploaded' | 'parsing' | 'parsed' | 'indexing' | 'ready' | 'failed'
  source_uri?: string
  checksum?: string
  index_version?: string
  updated_at?: string
}

export interface WorkflowStepConfig {
  name: string
  timeout_seconds: number
  on_error: 'stop' | 'continue'
}

export interface RuntimeConfig {
  model_provider: string
  model_name: string
  model_base_url: string
  model_api_key_configured: boolean
  model_timeout_seconds: number
  model_max_retries: number
  request_timeout_seconds: number
  rag_top_k: number
  rate_limit_requests: number
  rate_limit_window_seconds: number
  embedding_provider: string
  embedding_model: string
  vector_store_provider: string
  domain_plugin: string
  workflow_version: string
  published_config_version?: number
  system_prompt: string
  workflow_steps: WorkflowStepConfig[]
}

export interface SearchResult {
  document_id: string
  title: string
  content: string
  score: number
  metadata: Record<string, unknown>
  retrieval_sources: ('vector' | 'lexical' | 'reranked')[]
}

export interface EvaluationCaseResult {
  case_id: string
  query: string
  retrieved_document_ids: string[]
  answer: string
  retrieval_hit: boolean
  citation_present: boolean
  grounded: boolean
  no_context_safe: boolean
  judge_score: number
  judge_reason: string
}

export interface EvaluationReport {
  dataset_size: number
  retrieval_hit_rate: number
  citation_rate: number
  grounded_answer_rate: number
  no_context_precision: number
  overall_score: number
  cases: EvaluationCaseResult[]
}

export interface ChatMessage {
  role: Role
  content: string
  createdAt?: string
}

export interface Overview {
  tenant_count: number
  knowledge_base_count: number
  document_count: number
  enabled_knowledge_base_count: number
}

export interface ConfigVersion {
  config_id: string
  scope_type: 'platform' | 'tenant'
  scope_id: string
  version: number
  status: 'draft' | 'published' | 'archived'
  values: Record<string, unknown>
  note: string
  created_by: string
  created_at: string
  published_at?: string
}

export interface TaskJob {
  task_id: string
  task_name: string
  status: 'queued' | 'running' | 'succeeded' | 'retrying' | 'failed' | 'dead_letter'
  attempts: number
  max_attempts: number
  error?: string
  created_at: string
  updated_at: string
}

export interface WorkflowStepTrace {
  step: string
  status: 'succeeded' | 'failed' | 'skipped'
  duration_ms: number
  error?: string
}

export interface WorkflowRun {
  run_id: string
  conversation_id: string
  tenant_id: string
  workflow_version: string
  status: 'succeeded' | 'failed'
  steps: WorkflowStepTrace[]
  created_at: string
}

export interface EvaluationRun {
  run_id: string
  judge: 'rules' | 'llm'
  model_name: string
  plugin_id: string
  workflow_version: string
  overall_score: number
  dataset_size: number
  report: EvaluationReport
  created_at: string
}

export interface AuditLog {
  audit_id: string
  actor_id: string
  action: string
  resource_type: string
  resource_id?: string
  tenant_id?: string
  details: Record<string, unknown>
  created_at: string
}

export interface HandoffTicket {
  ticket_id: string
  tenant_id: string
  conversation_id?: string
  reason: string
  status: 'open' | 'assigned' | 'closed'
  created_at: string
}

export interface DomainPlugin {
  plugin_id: string
  name: string
  version: string
  workflow_version: string
  workflow_steps: string[]
  tools: string[]
}
