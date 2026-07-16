<script setup lang="ts">
import { ref } from 'vue'
import { ClipboardCheck, RefreshCw, Sparkles } from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'
import type { EvaluationReport } from '@/types'

const store = useAppStore()
const report = ref<EvaluationReport | null>(null)
const running = ref(false)
const judge = ref<'rules' | 'llm'>('rules')
async function run() { running.value = true; try { report.value = await api.evaluate(judge.value); store.evaluation = report.value } finally { running.value = false } }
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">QUALITY</p><h1>LLM / RAG 质量评测</h1><p class="muted">用固定数据集验证检索、引用、依据和无知识安全边界。</p></div><div class="head-actions"><select v-model="judge" class="select"><option value="rules">规则评测</option><option value="llm">LLM Judge</option></select><button class="button primary" :disabled="running" @click="run"><Sparkles :size="15" />{{ running ? '评测中…' : '运行评测' }}</button></div></div>
  <section v-if="report" class="metric-grid"><article class="metric teal"><span>Overall Score</span><strong>{{ Math.round(report.overall_score * 100) }}</strong><small>综合得分</small></article><article class="metric gold"><span>Retrieval Hit Rate</span><strong>{{ Math.round(report.retrieval_hit_rate * 100) }}%</strong><small>检索命中率</small></article><article class="metric violet"><span>Grounded Answer</span><strong>{{ Math.round(report.grounded_answer_rate * 100) }}%</strong><small>回答有依据</small></article><article class="metric green"><span>No-context Safety</span><strong>{{ Math.round(report.no_context_precision * 100) }}%</strong><small>无知识安全拒答</small></article></section>
  <section class="panel table-panel"><div class="panel-head"><div><h2>评测样本</h2><p class="muted">{{ report ? `${report.dataset_size} 个样本已完成` : '运行评测后查看逐条结果' }}</p></div><ClipboardCheck v-if="report" :size="18" class="muted-icon" /></div><div v-if="!report" class="empty-state"><RefreshCw :size="24" /><strong>尚未生成评测报告</strong><span>默认数据集覆盖理赔材料、犹豫期和无依据推荐。</span></div><div v-else class="table-wrap"><table><thead><tr><th>样本</th><th>检索</th><th>引用</th><th>依据</th><th>安全</th><th>得分</th><th>说明</th></tr></thead><tbody><tr v-for="item in report.cases" :key="item.case_id"><td><strong>{{ item.case_id }}</strong><small>{{ item.query }}</small></td><td><span class="status" :class="item.retrieval_hit ? 'green' : 'red'">{{ item.retrieval_hit ? '通过' : '失败' }}</span></td><td>{{ item.citation_present ? '有' : '无' }}</td><td>{{ item.grounded ? '通过' : '失败' }}</td><td>{{ item.no_context_safe ? '通过' : '失败' }}</td><td>{{ Math.round(item.judge_score * 100) }}</td><td>{{ item.judge_reason }}</td></tr></tbody></table></div></section>
</template>
