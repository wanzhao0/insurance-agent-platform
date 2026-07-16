<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ShieldCheck } from '@lucide/vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const router = useRouter()
const username = ref('admin')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true; error.value = ''
  try { await store.login(username.value, password.value); await router.push('/overview') }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '登录失败' }
  finally { loading.value = false }
}
</script>

<template>
  <main class="login-page"><section class="login-panel"><div class="login-mark"><ShieldCheck :size="25" /></div><p class="eyebrow">INSURANCE AGENT PLATFORM</p><h1>进入运营控制台</h1><p class="muted">管理租户、知识库、Agent 工作流与质量评测。</p><form @submit.prevent="submit"><label>用户名<input v-model="username" autocomplete="username" required /></label><label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label><div v-if="error" class="alert error">{{ error }}</div><button class="button primary wide" :disabled="loading">{{ loading ? '登录中…' : '登录控制台' }}</button></form><small class="muted">本地开发默认账号由 AGENT_LOCAL_ADMIN_* 配置。</small></section></main>
</template>
