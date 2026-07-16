import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import LoginView from '@/views/LoginView.vue'
import OverviewView from '@/views/OverviewView.vue'
import ChatView from '@/views/ChatView.vue'
import KnowledgeView from '@/views/KnowledgeView.vue'
import DocumentsView from '@/views/DocumentsView.vue'
import TenantsView from '@/views/TenantsView.vue'
import RuntimeView from '@/views/RuntimeView.vue'
import EvaluationsView from '@/views/EvaluationsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView },
    {
      path: '/', component: AppShell,
      children: [
        { path: '', redirect: '/overview' },
        { path: 'overview', component: OverviewView },
        { path: 'chat', component: ChatView },
        { path: 'knowledge', component: KnowledgeView },
        { path: 'documents', component: DocumentsView },
        { path: 'tenants', component: TenantsView },
        { path: 'runtime', component: RuntimeView },
        { path: 'evaluations', component: EvaluationsView },
      ],
    },
  ],
})
