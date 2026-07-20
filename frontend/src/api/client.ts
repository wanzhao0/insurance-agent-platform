import axios from 'axios'
import type {
  Document,
  AuditLog,
  ConfigVersion,
  DomainPlugin,
  EvaluationRun,
  HandoffTicket,
  EvaluationReport,
  KnowledgeBase,
  Overview,
  RuntimeConfig,
  SearchResult,
  Tenant,
  TaskJob,
  User,
  UserContext,
  WorkflowRun,
} from '@/types'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
export const http = axios.create({ baseURL: apiBaseUrl, timeout: 30000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('agent_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) localStorage.removeItem('agent_access_token')
    return Promise.reject(error)
  },
)

export const api = {
  async login(username: string, password: string) {
    const { data } = await http.post<{ access_token: string; user: UserContext }>(
      '/auth/login',
      { username, password },
    )
    localStorage.setItem('agent_access_token', data.access_token)
    return data.user
  },
  async me() {
    const { data } = await http.get<UserContext>('/auth/me')
    return data
  },
  async overview() {
    return (await http.get<Overview>('/admin/overview')).data
  },
  async tenants() {
    return (await http.get<Tenant[]>('/admin/tenants')).data
  },
  async updateTenant(id: string, payload: Record<string, unknown>) {
    return (await http.patch<Tenant>(`/admin/tenants/${encodeURIComponent(id)}`, payload)).data
  },
  async knowledgeBases() {
    return (await http.get<KnowledgeBase[]>('/admin/knowledge-bases')).data
  },
  async createKnowledgeBase(payload: Record<string, unknown>) {
    return (await http.post<KnowledgeBase>('/admin/knowledge-bases', payload)).data
  },
  async updateKnowledgeBase(id: string, payload: Record<string, unknown>) {
    return (await http.patch<KnowledgeBase>(`/admin/knowledge-bases/${encodeURIComponent(id)}`, payload)).data
  },
  async documents() {
    return (await http.get<Document[]>('/admin/documents')).data
  },
  async uploadDocument(file: File, knowledgeBaseId: string, category: string, title?: string) {
    const form = new FormData()
    form.append('file', file)
    form.append('knowledge_base_id', knowledgeBaseId)
    form.append('category', category)
    if (title?.trim()) form.append('title', title.trim())
    return (await http.post('/admin/documents/upload', form)).data
  },
  async deleteDocument(kbId: string, docId: string) {
    await http.delete(`/admin/documents/${encodeURIComponent(kbId)}/${encodeURIComponent(docId)}`)
  },
  async runtime() {
    return (await http.get<RuntimeConfig>('/admin/runtime')).data
  },
  async updateRuntime(payload: Record<string, unknown>) {
    return (await http.patch<RuntimeConfig>('/admin/runtime', payload)).data
  },
  async tools() {
    return (await http.get<{ name: string; description: string }[]>('/tools')).data
  },
  async evaluate(judge: 'rules' | 'llm' = 'rules') {
    return (await http.post<EvaluationReport>('/admin/evaluations/run', { judge })).data
  },
  async evaluationRuns() {
    return (await http.get<EvaluationRun[]>('/admin/evaluations')).data
  },
  async users() {
    return (await http.get<User[]>('/admin/users')).data
  },
  async createUser(payload: Record<string, unknown>) {
    return (await http.post<User>('/admin/users', payload)).data
  },
  async updateUser(id: string, payload: Record<string, unknown>) {
    return (await http.patch<User>(`/admin/users/${encodeURIComponent(id)}`, payload)).data
  },
  async configVersions() {
    return (await http.get<ConfigVersion[]>('/admin/config-versions')).data
  },
  async publishConfig(id: string) {
    return (await http.post<ConfigVersion>(`/admin/config-versions/${encodeURIComponent(id)}/publish`)).data
  },
  async tasks() {
    return (await http.get<TaskJob[]>('/admin/tasks')).data
  },
  async workflowRuns() {
    return (await http.get<WorkflowRun[]>('/admin/workflow-runs')).data
  },
  async auditLogs() {
    return (await http.get<AuditLog[]>('/admin/audit-logs')).data
  },
  async handoffs() {
    return (await http.get<HandoffTicket[]>('/admin/handoffs')).data
  },
  async updateHandoff(id: string, status: HandoffTicket['status']) {
    return (await http.patch<HandoffTicket>(`/admin/handoffs/${encodeURIComponent(id)}`, { status })).data
  },
  async plugins() {
    return (await http.get<DomainPlugin[]>('/admin/plugins')).data
  },
  async search(kbId: string, query: string) {
    return (await http.post<{ results: SearchResult[] }>(`/knowledge-bases/${kbId}/search`, { query })).data.results
  },
  async conversation(id: string) {
    return (await http.get(`/conversations/${encodeURIComponent(id)}`)).data
  },
}

export function streamChat(
  payload: Record<string, unknown>,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
) {
  const token = localStorage.getItem('agent_access_token')
  return fetch(`${apiBaseUrl}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
    signal,
  }).then(async (response) => {
    if (!response.ok || !response.body) throw new Error(`聊天请求失败（${response.status}）`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''
      for (const raw of events) {
        const event = raw.match(/^event: (.+)$/m)?.[1]
        const data = raw.match(/^data: (.+)$/m)?.[1]
        if (event && data) onEvent(event, JSON.parse(data))
      }
    }
  })
}
