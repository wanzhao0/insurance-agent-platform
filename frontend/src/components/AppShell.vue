<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { Bot, BookOpen, ClipboardCheck, FileText, Gauge, LogOut, Settings2, Users } from '@lucide/vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const route = useRoute()
const router = useRouter()
const navigation = [
  { to: '/overview', label: '运营总览', icon: Gauge },
  { to: '/chat', label: '客服工作台', icon: Bot },
  { to: '/knowledge', label: '知识库', icon: BookOpen },
  { to: '/documents', label: '文档管理', icon: FileText },
  { to: '/tenants', label: '租户配置', icon: Users },
  { to: '/runtime', label: '模型与工具', icon: Settings2 },
  { to: '/evaluations', label: '质量评测', icon: ClipboardCheck },
]
const pageTitle = computed(() => navigation.find((item) => route.path.startsWith(item.to))?.label || '平台概览')

onMounted(async () => {
  const loaded = await store.bootstrap()
  if (!loaded && store.authRequired) await router.replace('/login')
})

async function logout() {
  store.logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">保</div><div><strong>保险 Agent 平台</strong><span>Operations console</span></div></div>
      <div class="workspace"><span>当前工作区</span><strong>启明保险集团</strong><small>LOCAL / {{ store.activeTenant }}</small></div>
      <div class="nav-label">平台工作台</div>
      <nav class="nav" aria-label="主导航">
        <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-item">
          <component :is="item.icon" :size="17" stroke-width="1.8" /><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer"><span class="status-dot"></span><strong>平台状态 · 正常</strong><small>Vue 3 / FastAPI / Qdrant</small></div>
    </aside>
    <section class="main-shell">
      <header class="topbar">
        <div class="crumbs"><span>平台</span><span>/</span><strong>{{ pageTitle }}</strong></div>
        <div class="top-actions"><span class="env-pill">{{ store.user?.role === 'admin' ? 'ADMIN' : 'LOCAL' }}</span><span class="user-name">{{ store.user?.username || '本地管理员' }}</span><button class="icon-button" title="退出登录" @click="logout"><LogOut :size="16" /></button></div>
      </header>
      <main class="main-content">
        <div v-if="store.error" class="alert error">{{ store.error }} <button @click="store.refresh">重试</button></div>
        <RouterView />
      </main>
    </section>
  </div>
</template>
