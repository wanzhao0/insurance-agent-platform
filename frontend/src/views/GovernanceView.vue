<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  Activity,
  FileClock,
  History,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserCog,
  Workflow,
} from '@lucide/vue'
import { api } from '@/api/client'
import { useAppStore } from '@/stores/app'
import type {
  AuditLog,
  ConfigVersion,
  DomainPlugin,
  HandoffTicket,
  TaskJob,
  User,
  WorkflowRun,
} from '@/types'

type Tab = 'users' | 'configs' | 'automation' | 'handoffs' | 'audit'

const store = useAppStore()
const activeTab = ref<Tab>('users')
const loading = ref(false)
const message = ref('')
const users = ref<User[]>([])
const configs = ref<ConfigVersion[]>([])
const tasks = ref<TaskJob[]>([])
const workflows = ref<WorkflowRun[]>([])
const audits = ref<AuditLog[]>([])
const handoffs = ref<HandoffTicket[]>([])
const plugins = ref<DomainPlugin[]>([])
const newUser = reactive({ username: '', password: '', role: 'viewer' as User['role'], tenant_ids: ['demo'] })

const tabs: { id: Tab; label: string; icon: typeof UserCog }[] = [
  { id: 'users', label: '用户与权限', icon: UserCog },
  { id: 'configs', label: '配置版本', icon: History },
  { id: 'automation', label: '任务与工作流', icon: Workflow },
  { id: 'handoffs', label: '转人工工单', icon: ShieldCheck },
  { id: 'audit', label: '审计日志', icon: FileClock },
]

async function load() {
  loading.value = true
  message.value = ''
  try {
    ;[users.value, configs.value, tasks.value, workflows.value, audits.value, handoffs.value, plugins.value] =
      await Promise.all([
        api.users(),
        api.configVersions(),
        api.tasks(),
        api.workflowRuns(),
        api.auditLogs(),
        api.handoffs(),
        api.plugins(),
      ])
  } catch (error) {
    message.value = error instanceof Error ? error.message : '治理数据加载失败'
  } finally {
    loading.value = false
  }
}

async function createUser() {
  if (!newUser.username.trim() || newUser.password.length < 8) return
  await api.createUser({ ...newUser })
  Object.assign(newUser, { username: '', password: '', role: 'viewer', tenant_ids: ['demo'] })
  await load()
}

function toggleTenant(tenantId: string) {
  const index = newUser.tenant_ids.indexOf(tenantId)
  if (index >= 0) newUser.tenant_ids.splice(index, 1)
  else newUser.tenant_ids.push(tenantId)
}

async function saveUser(user: User) {
  await api.updateUser(user.user_id, {
    role: user.role,
    tenant_ids: user.tenant_ids,
    enabled: user.enabled,
  })
  await load()
}

async function publish(config: ConfigVersion) {
  if (!confirm(`确定发布 ${config.scope_id} v${config.version} 吗？`)) return
  await api.publishConfig(config.config_id)
  await Promise.all([load(), store.refresh()])
}

async function saveHandoff(ticket: HandoffTicket) {
  await api.updateHandoff(ticket.ticket_id, ticket.status)
  await load()
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function statusTone(value: string) {
  if (['published', 'succeeded', 'closed'].includes(value)) return 'green'
  if (['failed', 'dead_letter'].includes(value)) return 'red'
  if (['running', 'assigned', 'retrying'].includes(value)) return 'gold'
  return 'violet'
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <div>
      <p class="eyebrow">GOVERNANCE</p>
      <h1>平台治理</h1>
      <p class="muted">管理访问边界、配置发布、后台任务和审计记录。</p>
    </div>
    <button class="button" :disabled="loading" @click="load">
      <RefreshCw :size="15" />{{ loading ? '刷新中…' : '刷新' }}
    </button>
  </div>

  <div v-if="message" class="alert error">{{ message }}</div>
  <div class="tabs" role="tablist" aria-label="平台治理视图">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      class="tab-button"
      :class="{ active: activeTab === tab.id }"
      role="tab"
      @click="activeTab = tab.id"
    >
      <component :is="tab.icon" :size="15" />{{ tab.label }}
    </button>
  </div>

  <template v-if="activeTab === 'users'">
    <section class="panel">
      <div class="panel-head">
        <div><h2>新增用户</h2><p class="muted">为用户分配角色和可访问租户。</p></div>
        <span class="status green">{{ users.length }} 个账户</span>
      </div>
      <form class="form-grid governance-form" @submit.prevent="createUser">
        <label>用户名<input v-model="newUser.username" placeholder="例如 claims.operator" /></label>
        <label>初始密码<input v-model="newUser.password" type="password" minlength="8" /></label>
        <label>角色<select v-model="newUser.role"><option value="viewer">只读用户</option><option value="operator">运营人员</option><option value="admin">平台管理员</option></select></label>
        <fieldset class="tenant-selector">
          <legend>租户范围</legend>
          <label v-for="tenant in store.tenants" :key="tenant.tenant_id" class="check-option">
            <input type="checkbox" :checked="newUser.tenant_ids.includes(tenant.tenant_id)" @change="toggleTenant(tenant.tenant_id)" />
            <span>{{ tenant.name }}</span>
          </label>
        </fieldset>
        <div class="form-actions full"><button class="button primary"><Plus :size="15" />创建用户</button></div>
      </form>
    </section>
    <section class="panel table-panel">
      <div class="table-wrap"><table><thead><tr><th>用户</th><th>角色</th><th>租户范围</th><th>状态</th><th>更新时间</th><th></th></tr></thead><tbody>
        <tr v-for="user in users" :key="user.user_id">
          <td><strong>{{ user.username }}</strong><small>{{ user.user_id }}</small></td>
          <td><select v-model="user.role" class="table-select"><option value="viewer">只读用户</option><option value="operator">运营人员</option><option value="admin">平台管理员</option></select></td>
          <td>{{ user.tenant_ids.includes('*') ? '全部租户' : user.tenant_ids.join('、') || '未分配' }}</td>
          <td><button class="status" :class="user.enabled ? 'green' : 'red'" @click="user.enabled = !user.enabled">{{ user.enabled ? '启用' : '停用' }}</button></td>
          <td>{{ formatDate(user.updated_at) }}</td>
          <td><button class="button compact" @click="saveUser(user)">保存</button></td>
        </tr>
      </tbody></table></div>
    </section>
  </template>

  <template v-else-if="activeTab === 'configs'">
    <section class="panel">
      <div class="panel-head"><div><h2>当前领域插件</h2><p class="muted">插件约束业务工具，配置版本管理提示词、模型和工作流。</p></div></div>
      <div class="stack-list"><div v-for="plugin in plugins" :key="plugin.plugin_id" class="stack-item"><Activity :size="18" /><div><strong>{{ plugin.name }} · {{ plugin.version }}</strong><small>{{ plugin.workflow_steps.join(' → ') }} · {{ plugin.tools.join(' / ') }}</small></div><span class="status green">已加载</span></div></div>
    </section>
    <section class="panel table-panel">
      <div class="panel-head"><div><h2>配置版本</h2><p class="muted">重新发布历史版本即可回滚；运行配置页保存时自动生成新版本。</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>范围</th><th>版本</th><th>说明</th><th>创建人</th><th>创建时间</th><th>状态</th><th></th></tr></thead><tbody>
        <tr v-for="config in configs" :key="config.config_id"><td><strong>{{ config.scope_id }}</strong><small>{{ config.scope_type }}</small></td><td>v{{ config.version }}</td><td>{{ config.note || '无说明' }}</td><td>{{ config.created_by }}</td><td>{{ formatDate(config.created_at) }}</td><td><span class="status" :class="statusTone(config.status)">{{ config.status }}</span></td><td><button v-if="config.status !== 'published'" class="button compact" @click="publish(config)">发布</button></td></tr>
      </tbody></table></div>
    </section>
  </template>

  <template v-else-if="activeTab === 'automation'">
    <section class="panel table-panel"><div class="panel-head"><div><h2>异步任务</h2><p class="muted">索引任务支持重试、延迟重试和死信留档。</p></div></div><div class="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>尝试次数</th><th>更新时间</th><th>错误</th></tr></thead><tbody><tr v-for="task in tasks" :key="task.task_id"><td><strong>{{ task.task_name }}</strong><small>{{ task.task_id }}</small></td><td><span class="status" :class="statusTone(task.status)">{{ task.status }}</span></td><td>{{ task.attempts }} / {{ task.max_attempts }}</td><td>{{ formatDate(task.updated_at) }}</td><td>{{ task.error || '—' }}</td></tr><tr v-if="!tasks.length"><td colspan="5" class="empty-row">暂无后台任务</td></tr></tbody></table></div></section>
    <section class="panel table-panel"><div class="panel-head"><div><h2>工作流运行</h2><p class="muted">记录每个智能体步骤的耗时和结果。</p></div></div><div class="table-wrap"><table><thead><tr><th>会话</th><th>租户</th><th>版本</th><th>步骤</th><th>状态</th><th>时间</th></tr></thead><tbody><tr v-for="run in workflows" :key="run.run_id"><td><strong>{{ run.conversation_id }}</strong><small>{{ run.run_id }}</small></td><td>{{ run.tenant_id }}</td><td>{{ run.workflow_version }}</td><td><span v-for="step in run.steps" :key="step.step" class="trace-step">{{ step.step }} {{ Math.round(step.duration_ms) }}ms</span></td><td><span class="status" :class="statusTone(run.status)">{{ run.status }}</span></td><td>{{ formatDate(run.created_at) }}</td></tr><tr v-if="!workflows.length"><td colspan="6" class="empty-row">尚无工作流运行记录</td></tr></tbody></table></div></section>
  </template>

  <section v-else-if="activeTab === 'handoffs'" class="panel table-panel">
    <div class="panel-head"><div><h2>转人工工单</h2><p class="muted">跟进证据不足、敏感问题和客户主动转人工请求。</p></div></div>
    <div class="table-wrap"><table><thead><tr><th>工单</th><th>租户</th><th>原因</th><th>会话</th><th>创建时间</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="ticket in handoffs" :key="ticket.ticket_id"><td><strong>{{ ticket.ticket_id }}</strong></td><td>{{ ticket.tenant_id }}</td><td>{{ ticket.reason }}</td><td>{{ ticket.conversation_id || '—' }}</td><td>{{ formatDate(ticket.created_at) }}</td><td><select v-model="ticket.status" class="table-select"><option value="open">待处理</option><option value="assigned">处理中</option><option value="closed">已关闭</option></select></td><td><button class="button compact" @click="saveHandoff(ticket)">保存</button></td></tr><tr v-if="!handoffs.length"><td colspan="7" class="empty-row">暂无转人工工单</td></tr></tbody></table></div>
  </section>

  <section v-else class="panel table-panel">
    <div class="panel-head"><div><h2>审计日志</h2><p class="muted">保留后台关键变更的操作者、资源和时间。</p></div></div>
    <div class="table-wrap"><table><thead><tr><th>操作</th><th>操作者</th><th>资源</th><th>租户</th><th>详情</th><th>时间</th></tr></thead><tbody><tr v-for="audit in audits" :key="audit.audit_id"><td><strong>{{ audit.action }}</strong></td><td>{{ audit.actor_id }}</td><td>{{ audit.resource_type }} / {{ audit.resource_id || '—' }}</td><td>{{ audit.tenant_id || '全局' }}</td><td><small class="details-cell">{{ JSON.stringify(audit.details) }}</small></td><td>{{ formatDate(audit.created_at) }}</td></tr><tr v-if="!audits.length"><td colspan="6" class="empty-row">暂无审计记录</td></tr></tbody></table></div>
  </section>
</template>
