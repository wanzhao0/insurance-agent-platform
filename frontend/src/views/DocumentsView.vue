<script setup lang="ts">
import { ref } from 'vue'
import { FileUp, RefreshCw, Trash2 } from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const file = ref<File | null>(null)
const category = ref('理赔服务')
const title = ref('')
const selectedKb = ref(store.activeKnowledgeBase)
const uploading = ref(false)
function choose(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null }
async function upload() { if (!file.value) return; uploading.value = true; try { await api.uploadDocument(file.value, selectedKb.value, category.value, title.value); file.value = null; title.value = ''; await store.refresh() } finally { uploading.value = false } }
async function remove(doc: { knowledge_base_id: string; document_id: string }) { if (!confirm(`确定删除“${doc.document_id}”吗？`)) return; await api.deleteDocument(doc.knowledge_base_id, doc.document_id); await store.refresh() }
function statusLabel(status: string) { return ({ uploaded: '已上传', parsing: '解析中', parsed: '待索引', indexing: '索引中', ready: '可检索', failed: '失败' } as Record<string, string>)[status] || status }
function statusTone(status: string) { return status === 'ready' ? 'green' : status === 'failed' ? 'red' : 'gold' }
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">DOCUMENTS</p><h1>文档管理</h1><p class="muted">上传后解析、分块、Embedding 并进入向量索引。</p></div><button class="button" @click="store.refresh"><RefreshCw :size="15" />刷新</button></div>
  <section class="panel upload-panel"><div class="panel-head"><div><h2>上传知识文档</h2><p class="muted">支持 Markdown、PDF、Word、Excel、PPTX、CSV 和 JSON。</p></div></div><form class="upload-form" @submit.prevent="upload"><label class="file-drop"><FileUp :size="22" /><strong>{{ file?.name || '选择要上传的文件' }}</strong><small>单文件上限 10 MiB</small><input type="file" accept=".md,.markdown,.txt,.csv,.tsv,.json,.pdf,.docx,.pptx,.xlsx,.xlsm,.xls" @change="choose" /></label><div class="form-grid"><label>归属知识库<select v-model="selectedKb"><option v-for="kb in store.knowledgeBases.filter((item) => item.enabled)" :key="kb.knowledge_base_id" :value="kb.knowledge_base_id">{{ kb.name }}</option></select></label><label>分类<select v-model="category"><option>产品条款</option><option>理赔服务</option><option>客服话术</option><option>业务流程</option></select></label><label class="full">覆盖标题（可选）<input v-model="title" placeholder="默认使用文件名" /></label></div><div class="form-actions"><button class="button primary" :disabled="!file || uploading"><FileUp :size="15" />{{ uploading ? '上传处理中…' : '上传并进入索引' }}</button></div></form></section>
  <section class="panel table-panel"><div class="panel-head"><div><h2>文档列表</h2><p class="muted">共 {{ store.documents.length }} 个文档</p></div></div><div class="table-wrap"><table><thead><tr><th>文档</th><th>知识库</th><th>分类</th><th>版本</th><th>索引版本</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="doc in store.documents" :key="`${doc.knowledge_base_id}-${doc.document_id}`"><td><strong>{{ doc.title }}</strong><small>{{ doc.document_id }} · {{ doc.content.slice(0, 80) }}…</small></td><td>{{ doc.knowledge_base_id }}</td><td>{{ doc.metadata.category || '未分类' }}</td><td>v{{ doc.version }}</td><td>{{ doc.index_version || '—' }}</td><td><span class="status" :class="statusTone(doc.status)">{{ statusLabel(doc.status) }}</span></td><td><button class="icon-button danger-icon" title="删除文档" @click="remove(doc)"><Trash2 :size="15" /></button></td></tr></tbody></table></div></section>
</template>
