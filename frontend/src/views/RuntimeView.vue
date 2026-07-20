<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { CheckCircle2, Cpu, Database, Plus, Save, Trash2, Workflow } from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'
import type { RuntimeConfig, WorkflowStepConfig } from '@/types'

const store = useAppStore()
const saving = ref(false)
const saved = ref(false)
const form = reactive({
  model_provider: 'mock',
  model_name: '',
  model_base_url: '',
  model_timeout_seconds: 45,
  request_timeout_seconds: 60,
  rag_top_k: 4,
  rate_limit_requests: 60,
  system_prompt: '',
  workflow_version: '',
  workflow_steps: [] as WorkflowStepConfig[],
})

watch(
  () => store.runtime,
  (runtime: RuntimeConfig | null) => {
    if (!runtime) return
    Object.assign(form, runtime, { workflow_steps: runtime.workflow_steps.map((step) => ({ ...step })) })
  },
  { immediate: true },
)

function addStep() {
  form.workflow_steps.push({ name: 'safety_review', timeout_seconds: 10, on_error: 'stop' })
}

function removeStep(index: number) {
  if (form.workflow_steps.length > 1) form.workflow_steps.splice(index, 1)
}

async function save() {
  saving.value = true
  saved.value = false
  try {
    await api.updateRuntime(form)
    await store.refresh()
    saved.value = true
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-head">
    <div>
      <p class="eyebrow">RUNTIME</p>
      <h1>模型与工作流</h1>
      <p class="muted">统一管理模型连接、检索参数、系统提示词和智能体执行步骤。</p>
    </div>
    <div class="head-actions">
      <span v-if="saved" class="status green">配置已发布</span>
      <button class="button primary" :disabled="saving" @click="save">
        <Save :size="15" />{{ saving ? '发布中…' : '保存并发布' }}
      </button>
    </div>
  </div>

  <div class="content-grid equal">
    <section class="panel">
      <div class="panel-head">
        <div><h2>模型连接</h2><p class="muted">API Key 仅从服务端环境变量读取</p></div>
        <span class="status" :class="store.runtime?.model_api_key_configured ? 'green' : 'gold'">
          <CheckCircle2 :size="13" />{{ store.runtime?.model_api_key_configured ? '已配置' : '未配置' }}
        </span>
      </div>
      <form class="form-grid" @submit.prevent="save">
        <label>Provider<select v-model="form.model_provider"><option value="mock">Mock / 本地演示</option><option value="openai-compatible">OpenAI Compatible</option></select></label>
        <label>模型名称<input v-model="form.model_name" /></label>
        <label class="full">Base URL<input v-model="form.model_base_url" /></label>
        <label>模型超时（秒）<input v-model.number="form.model_timeout_seconds" type="number" min="1" /></label>
        <label>请求超时（秒）<input v-model.number="form.request_timeout_seconds" type="number" min="1" /></label>
        <label>检索 Top K<input v-model.number="form.rag_top_k" type="number" min="1" max="20" /></label>
        <label>限流请求数<input v-model.number="form.rate_limit_requests" type="number" min="1" /></label>
      </form>
    </section>

    <section class="panel">
      <div class="panel-head"><div><h2>基础设施</h2><p class="muted">当前适配器与发布版本</p></div><span class="status violet">配置 v{{ store.runtime?.published_config_version || '环境' }}</span></div>
      <div class="stack-list">
        <div class="stack-item"><Cpu :size="18" /><div><strong>Embedding</strong><small>{{ store.runtime?.embedding_provider }} · {{ store.runtime?.embedding_model }}</small></div><span class="status green">就绪</span></div>
        <div class="stack-item"><Database :size="18" /><div><strong>Vector Store</strong><small>{{ store.runtime?.vector_store_provider }}</small></div><span class="status green">就绪</span></div>
        <div class="stack-item"><Workflow :size="18" /><div><strong>{{ store.runtime?.domain_plugin }}</strong><small>{{ form.workflow_version }}</small></div><span class="status green">已加载</span></div>
      </div>
      <div class="context-box">生产部署由 PostgreSQL 持久化配置，Redis 向其他实例广播发布事件。</div>
    </section>
  </div>

  <section class="panel">
    <div class="panel-head"><div><h2>系统提示词</h2><p class="muted">作为每次会话的领域约束和安全边界。</p></div></div>
    <div class="form-grid"><label class="full"><textarea v-model="form.system_prompt" class="prompt-editor" /></label></div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <div><h2>智能体工作流</h2><p class="muted">按顺序执行，每一步独立设置超时和失败策略。</p></div>
      <button class="button compact" @click="addStep"><Plus :size="14" />添加步骤</button>
    </div>
    <div class="workflow-editor-head"><span>顺序</span><span>智能体步骤</span><span>超时</span><span>失败策略</span><span></span></div>
    <div v-for="(step, index) in form.workflow_steps" :key="`${step.name}-${index}`" class="workflow-editor-row">
      <span class="step-index">{{ String(index + 1).padStart(2, '0') }}</span>
      <select v-model="step.name"><option value="knowledge_retrieval">知识检索 Agent</option><option value="safety_review">安全审查 Agent</option></select>
      <label class="number-field"><input v-model.number="step.timeout_seconds" type="number" min="1" max="600" /><span>秒</span></label>
      <select v-model="step.on_error"><option value="stop">停止执行</option><option value="continue">继续下一步</option></select>
      <button class="icon-button danger-icon" title="删除步骤" :disabled="form.workflow_steps.length === 1" @click="removeStep(index)"><Trash2 :size="15" /></button>
    </div>
    <div class="workflow-version"><label>工作流版本<input v-model="form.workflow_version" /></label></div>
  </section>

  <section class="panel">
    <div class="panel-head"><div><h2>已注册工具</h2><p class="muted">工具参数由服务端注入租户和知识库边界。</p></div></div>
    <div class="tool-list"><div v-for="tool in store.tools" :key="tool.name" class="tool-row"><div><strong>{{ tool.name }}</strong><p>{{ tool.description }}</p></div><span class="status green">模型可调用</span></div></div>
  </section>
</template>
