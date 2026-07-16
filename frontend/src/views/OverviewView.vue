<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowUpRight, Database, FileCheck2, Play, RefreshCw, Users } from '@lucide/vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const metrics = computed(() => [
  { label: '租户', value: store.overview?.tenant_count ?? 0, foot: '已纳入平台', icon: Users, tone: 'teal' },
  { label: '知识库', value: store.overview?.knowledge_base_count ?? 0, foot: `${store.overview?.enabled_knowledge_base_count ?? 0} 个已启用`, icon: Database, tone: 'gold' },
  { label: '文档', value: store.overview?.document_count ?? 0, foot: '已进入文档仓库', icon: FileCheck2, tone: 'violet' },
  { label: '注册工具', value: store.tools.length, foot: '可由模型触发', icon: Play, tone: 'green' },
])
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">OPERATIONS</p><h1>平台概览</h1><p class="muted">查看系统运行状态、知识库规模和 Agent 质量。</p></div><button class="button" @click="store.refresh"><RefreshCw :size="15" />刷新数据</button></div>
  <div class="metric-grid"><article v-for="metric in metrics" :key="metric.label" class="metric" :class="metric.tone"><component :is="metric.icon" :size="17" /><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.foot }}</small></article></div>
  <div class="content-grid"><section class="panel"><div class="panel-head"><div><h2>当前运行链路</h2><p class="muted">从客户问题到可审计答案</p></div><span class="status green">正常</span></div><div class="pipeline"><div><span>01</span><strong>租户上下文</strong><small>权限与知识库范围</small></div><i></i><div><span>02</span><strong>Embedding + RAG</strong><small>{{ store.runtime?.vector_store_provider || 'qdrant-local' }}</small></div><i></i><div><span>03</span><strong>Agent 工作流</strong><small>检索 → 安全审查</small></div><i></i><div><span>04</span><strong>SSE 答复</strong><small>引用与工具事件</small></div></div></section><section class="panel"><div class="panel-head"><div><h2>快捷操作</h2><p class="muted">常用管理入口</p></div></div><div class="quick-list"><RouterLink to="/chat" class="quick-action">打开客服工作台<ArrowUpRight :size="15" /></RouterLink><RouterLink to="/documents" class="quick-action">上传知识文档<ArrowUpRight :size="15" /></RouterLink><RouterLink to="/evaluations" class="quick-action">运行质量评测<ArrowUpRight :size="15" /></RouterLink><RouterLink to="/runtime" class="quick-action">检查模型配置<ArrowUpRight :size="15" /></RouterLink></div></section></div>
  <section class="panel table-panel"><div class="panel-head"><div><h2>知识库状态</h2><p class="muted">按租户查看当前索引范围</p></div><RouterLink to="/knowledge" class="text-link">管理知识库 <ArrowUpRight :size="14" /></RouterLink></div><div class="table-wrap"><table><thead><tr><th>知识库</th><th>租户</th><th>文档</th><th>版本</th><th>状态</th></tr></thead><tbody><tr v-for="kb in store.knowledgeBases" :key="kb.knowledge_base_id"><td><strong>{{ kb.name }}</strong><small>{{ kb.knowledge_base_id }}</small></td><td>{{ kb.tenant_id }}</td><td>{{ kb.document_count }}</td><td>v{{ kb.version }}</td><td><span class="status" :class="kb.enabled ? 'green' : 'red'">{{ kb.enabled ? '启用' : '停用' }}</span></td></tr></tbody></table></div></section>
</template>
