<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Bot, BookOpen, Send, Square, Wrench } from '@lucide/vue'
import { streamChat } from '@/api/client'
import { useAppStore } from '@/stores/app'
import type { ChatMessage, SearchResult } from '@/types'

const store = useAppStore()
const input = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([{ role: 'assistant', content: '您好，我可以根据当前租户知识库协助查询保险服务信息。' }])
const citations = ref<SearchResult[]>([])
const events = ref<string[]>([])
const conversationId = ref(crypto.randomUUID())
const abortController = ref<AbortController | null>(null)

async function send() {
  const content = input.value.trim()
  if (!content || sending.value) return
  input.value = ''; sending.value = true; citations.value = []; events.value = []
  messages.value.push({ role: 'user', content }, { role: 'assistant', content: '' })
  const assistant = messages.value[messages.value.length - 1]
  abortController.value = new AbortController()
  try {
    await streamChat({ tenant_id: store.activeTenant, knowledge_base_id: store.activeKnowledgeBase, conversation_id: conversationId.value, messages: [{ role: 'user', content }] }, (event, data) => {
      if (event === 'token' && typeof data.content === 'string') assistant.content += data.content
      if (event === 'citation' && data.citation) citations.value.push(data.citation as SearchResult)
      if (event === 'tool_call') events.value.push(String(data.tool_name || 'tool'))
      void nextTick()
    }, abortController.value.signal)
  } catch (caught) {
    assistant.content = caught instanceof Error ? caught.message : '请求失败'
  } finally { sending.value = false; abortController.value = null }
}

function stop() { abortController.value?.abort(); sending.value = false }
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">CUSTOMER SERVICE</p><h1>客服工作台</h1><p class="muted">当前知识库：{{ store.knowledgeBases.find((item) => item.knowledge_base_id === store.activeKnowledgeBase)?.name || store.activeKnowledgeBase }}</p></div><div class="toolbar-right"><select v-model="store.activeTenant" class="select"><option v-for="tenant in store.tenants" :key="tenant.tenant_id" :value="tenant.tenant_id">{{ tenant.name }}</option></select><select v-model="store.activeKnowledgeBase" class="select"><option v-for="kb in store.knowledgeBases.filter((item) => item.tenant_id === store.activeTenant && item.enabled)" :key="kb.knowledge_base_id" :value="kb.knowledge_base_id">{{ kb.name }}</option></select></div></div>
  <div class="workspace-layout"><section class="chat-main"><div class="chat-header"><div><strong>客服对话</strong><small>Agent 会先触发知识库工具，再经过安全审查</small></div><button v-if="sending" class="button" @click="stop"><Square :size="14" />停止</button></div><div class="chat-messages"><article v-for="(message, index) in messages" :key="index" class="chat-message" :class="message.role"><div class="message-meta">{{ message.role === 'user' ? '您' : 'Agent' }}</div>{{ message.content || (sending && index === messages.length - 1 ? '正在检索并生成…' : '') }}</article></div><form class="chat-composer" @submit.prevent="send"><textarea v-model="input" placeholder="输入客户问题，例如：理赔需要准备什么材料？" @keydown.enter.exact.prevent="send" /><button class="button primary icon-text" :disabled="sending"><Send :size="15" />发送</button></form></section><aside class="inspector"><div class="inspector-head"><h2>本次运行</h2><p class="muted">工具和引用实时记录</p></div><div class="inspector-section"><div class="inspector-label"><Wrench :size="14" />工具调用</div><div v-if="events.length" class="event-list"><span v-for="(event, index) in events" :key="index" class="event-chip">{{ event }}</span></div><p v-else class="empty-inline">尚未触发工具</p></div><div class="inspector-section"><div class="inspector-label"><BookOpen :size="14" />回答依据</div><button v-for="citation in citations" :key="citation.document_id" class="citation"><strong>{{ citation.title }}</strong><span>{{ citation.content.slice(0, 130) }}…</span></button><p v-if="!citations.length" class="empty-inline">完成一次对话后显示检索证据</p></div><div class="inspector-section context-box"><Bot :size="15" />没有直接证据时，Agent 会明确说明无法确认，并建议人工复核。</div></aside></div>
</template>
