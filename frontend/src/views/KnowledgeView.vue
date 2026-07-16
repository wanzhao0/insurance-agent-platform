<script setup lang="ts">
import { ref } from 'vue'
import { Plus, RefreshCw, ToggleLeft } from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const showForm = ref(false)
const form = ref({ id: '', tenant_id: 'demo', name: '', description: '' })
const saving = ref(false)
async function create() {
  saving.value = true
  try { await api.createKnowledgeBase({ knowledge_base_id: form.value.id, ...form.value }); showForm.value = false; form.value = { id: '', tenant_id: 'demo', name: '', description: '' }; await store.refresh() }
  finally { saving.value = false }
}
async function toggle(kb: { knowledge_base_id: string; enabled: boolean }) { await api.updateKnowledgeBase(kb.knowledge_base_id, { enabled: !kb.enabled }); await store.refresh() }
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">KNOWLEDGE</p><h1>知识库</h1><p class="muted">管理行业知识源、租户边界、版本和检索范围。</p></div><div class="head-actions"><button class="button" @click="store.refresh"><RefreshCw :size="15" />刷新</button><button class="button primary" @click="showForm = !showForm"><Plus :size="15" />新建知识库</button></div></div>
  <section v-if="showForm" class="panel form-panel"><div class="panel-head"><h2>新建知识库</h2></div><form class="form-grid" @submit.prevent="create"><label>知识库 ID<input v-model="form.id" pattern="[a-zA-Z0-9_-]+" required placeholder="travel-products" /></label><label>所属租户<select v-model="form.tenant_id"><option v-for="tenant in store.tenants" :key="tenant.tenant_id" :value="tenant.tenant_id">{{ tenant.name }}</option></select></label><label>显示名称<input v-model="form.name" required /></label><label class="full">用途说明<textarea v-model="form.description" required /></label><div class="form-actions full"><button class="button" type="button" @click="showForm = false">取消</button><button class="button primary" :disabled="saving">创建</button></div></form></section>
  <section class="panel table-panel"><div class="panel-head"><div><h2>全部知识库</h2><p class="muted">共 {{ store.knowledgeBases.length }} 个配置</p></div></div><div class="table-wrap"><table><thead><tr><th>知识库</th><th>租户</th><th>文档数</th><th>版本</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="kb in store.knowledgeBases" :key="kb.knowledge_base_id"><td><strong>{{ kb.name }}</strong><small>{{ kb.knowledge_base_id }} · {{ kb.description }}</small></td><td>{{ kb.tenant_id }}</td><td>{{ kb.document_count }}</td><td>v{{ kb.version }}</td><td><span class="status" :class="kb.enabled ? 'green' : 'red'">{{ kb.enabled ? '启用' : '停用' }}</span></td><td><button class="icon-button" :title="kb.enabled ? '停用' : '启用'" @click="toggle(kb)"><ToggleLeft :size="16" /></button></td></tr></tbody></table></div></section>
</template>
