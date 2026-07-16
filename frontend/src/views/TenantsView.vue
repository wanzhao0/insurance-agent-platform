<script setup lang="ts">
import { ref } from 'vue'
import { Save, Users } from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const editing = ref<string | null>(null)
const saving = ref(false)
async function save(tenant: { tenant_id: string; plan: string; default_knowledge_base_id: string; enabled: boolean }) { saving.value = true; try { await api.updateTenant(tenant.tenant_id, { plan: tenant.plan, default_knowledge_base_id: tenant.default_knowledge_base_id, enabled: tenant.enabled }); editing.value = null; await store.refresh() } finally { saving.value = false } }
</script>

<template>
  <div class="page-head"><div><p class="eyebrow">TENANTS</p><h1>租户配置</h1><p class="muted">管理租户边界、默认知识库和业务套餐。</p></div><span class="status green"><Users :size="14" />{{ store.tenants.length }} 个租户</span></div>
  <section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>租户</th><th>套餐</th><th>默认知识库</th><th>知识库数</th><th>版本</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="tenant in store.tenants" :key="tenant.tenant_id"><td><strong>{{ tenant.name }}</strong><small>{{ tenant.tenant_id }}</small></td><td><select v-model="tenant.plan" class="table-select" :disabled="editing !== tenant.tenant_id"><option>企业版</option><option>合作版</option><option>沙箱</option></select></td><td><select v-model="tenant.default_knowledge_base_id" class="table-select" :disabled="editing !== tenant.tenant_id"><option v-for="kb in store.knowledgeBases.filter((item) => item.tenant_id === tenant.tenant_id)" :key="kb.knowledge_base_id" :value="kb.knowledge_base_id">{{ kb.name }}</option></select></td><td>{{ tenant.knowledge_base_count }}</td><td>v{{ tenant.version }}</td><td><button class="status" :class="tenant.enabled ? 'green' : 'red'" @click="tenant.enabled = !tenant.enabled">{{ tenant.enabled ? '正常' : '停用' }}</button></td><td><button v-if="editing !== tenant.tenant_id" class="button compact" @click="editing = tenant.tenant_id">编辑</button><button v-else class="button primary compact" :disabled="saving" @click="save(tenant)"><Save :size="13" />保存</button></td></tr></tbody></table></div></section>
</template>
