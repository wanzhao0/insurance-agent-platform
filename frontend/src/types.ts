export type Role = 'system' | 'user' | 'assistant' | 'tool'

export interface UserContext {
  user_id: string
  username: string
  role: 'admin' | 'operator' | 'viewer'
  tenant_ids: string[]
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
}

export interface SearchResult {
  document_id: string
  title: string
  content: string
  score: number
  metadata: Record<string, unknown>
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
