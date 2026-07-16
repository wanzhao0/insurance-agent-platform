<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { CheckCircle2, Cpu, Database, Save, Workflow } from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const saving = ref(false)
const form = reactive({ model_provider: 'mock', model_name: '', model_base_url: '', model_timeout_seconds: 45, request_timeout_seconds: 60, rag_top_k: 4, rate_limit_requests: 60 })
watch(() => store.runtime, (runtime) => { if (runtime) Object.assign(form, runtime) }, { immediate: true })
async function save() { saving.value = true; try { await api.updateRuntime(form); await store.refresh() } finally { saving.value = false } }
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">RUNTIME</p><h1>模型与工具</h1><p class="muted">配置模型连接、Embedding、向量库和 Agent 工作流。</p></div><button class="button primary" :disabled="saving" @click="save"><Save :size="15" />保存运行配置</button></div>
  <div class="content-grid equal"><section class="panel"><div class="panel-head"><div><h2>模型连接</h2><p class="muted">密钥只从服务端环境变量读取</p></div><span class="status" :class="store.runtime?.model_api_key_configured ? 'green' : 'gold'"><CheckCircle2 :size="13" />{{ store.runtime?.model_api_key_configured ? '已配置' : '未配置' }}</span></div><form class="form-grid form-panel" @submit.prevent="save"><label>Provider<select v-model="form.model_provider"><option value="mock">Mock / 本地演示</option><option value="openai-compatible">OpenAI Compatible</option></select></label><label>模型名称<input v-model="form.model_name" /></label><label class="full">Base URL<input v-model="form.model_base_url" /></label><label>模型超时（秒）<input v-model.number="form.model_timeout_seconds" type="number" min="1" /></label><label>请求超时（秒）<input v-model.number="form.request_timeout_seconds" type="number" min="1" /></label><label>检索 Top K<input v-model.number="form.rag_top_k" type="number" min="1" max="20" /></label><label>限流请求数<input v-model.number="form.rate_limit_requests" type="number" min="1" /></label></form></section><section class="panel"><div class="panel-head"><div><h2>基础设施</h2><p class="muted">可替换适配器运行状态</p></div></div><div class="stack-list"><div class="stack-item"><Cpu :size="18" /><div><strong>Embedding</strong><small>{{ store.runtime?.embedding_provider }} · {{ store.runtime?.embedding_model }}</small></div><span class="status green">就绪</span></div><div class="stack-item"><Database :size="18" /><div><strong>Vector Store</strong><small>{{ store.runtime?.vector_store_provider }}</small></div><span class="status green">就绪</span></div><div class="stack-item"><Workflow :size="18" /><div><strong>Workflow</strong><small>知识检索 Agent → 安全审查 Agent</small></div><span class="status green">启用</span></div></div><div class="context-box">生产环境建议使用远程 PostgreSQL、Redis 和 Qdrant，并通过 Alembic 完成迁移。</div></section></div>
  <section class="panel"><div class="panel-head"><div><h2>已注册工具</h2><p class="muted">工具参数由服务端强制注入租户范围</p></div></div><div class="tool-list"><div v-for="tool in store.tools" :key="tool.name" class="tool-row"><div><strong>{{ tool.name }}</strong><p>{{ tool.description }}</p></div><span class="status green">模型可调用</span></div></div></section>
</template>
