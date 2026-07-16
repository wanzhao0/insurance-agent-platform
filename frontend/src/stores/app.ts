import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { Document, EvaluationReport, KnowledgeBase, Overview, RuntimeConfig, Tenant, UserContext } from '@/types'

export const useAppStore = defineStore('app', () => {
  const user = ref<UserContext | null>(null)
  const overview = ref<Overview | null>(null)
  const tenants = ref<Tenant[]>([])
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const documents = ref<Document[]>([])
  const runtime = ref<RuntimeConfig | null>(null)
  const tools = ref<{ name: string; description: string }[]>([])
  const evaluation = ref<EvaluationReport | null>(null)
  const loading = ref(false)
  const error = ref('')
  const authRequired = ref(false)
  const activeTenant = ref('demo')
  const activeKnowledgeBase = ref('insurance-general')
  const isAdmin = computed(() => user.value?.role === 'admin' || !user.value)

  async function bootstrap() {
    loading.value = true
    error.value = ''
    authRequired.value = false
    try {
      user.value = await api.me()
      const [nextOverview, nextTenants, nextKnowledgeBases, nextDocuments, nextRuntime, nextTools] = await Promise.all([
        api.overview(), api.tenants(), api.knowledgeBases(), api.documents(), api.runtime(), api.tools(),
      ])
      overview.value = nextOverview
      tenants.value = nextTenants
      knowledgeBases.value = nextKnowledgeBases
      documents.value = nextDocuments
      runtime.value = nextRuntime
      tools.value = nextTools
      if (!knowledgeBases.value.some((item) => item.knowledge_base_id === activeKnowledgeBase.value)) {
        activeKnowledgeBase.value = knowledgeBases.value[0]?.knowledge_base_id || 'insurance-general'
      }
      return true
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '加载平台数据失败'
      authRequired.value = (caught as { response?: { status?: number } }).response?.status === 401
      return false
    } finally {
      loading.value = false
    }
  }

  async function login(username: string, password: string) {
    user.value = await api.login(username, password)
    authRequired.value = false
    await bootstrap()
  }

  function logout() {
    localStorage.removeItem('agent_access_token')
    user.value = null
  }

  async function refresh() {
    await bootstrap()
  }

  return {
    user, overview, tenants, knowledgeBases, documents, runtime, tools, evaluation,
    loading, error, authRequired, activeTenant, activeKnowledgeBase, isAdmin, bootstrap, login, logout, refresh,
  }
})
