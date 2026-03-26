import axios from 'axios'
import type { DashboardResponse, HistoryResponse, ProductivityBreakdown } from './types'

const baseURL = ''
const api = axios.create({
  baseURL,
  timeout: 30000,
})

export async function getDashboard(day: string, deviceId?: string): Promise<DashboardResponse> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  const { data } = await api.get(`/api/v1/dashboard/${day}`, { params })
  return data
}

export async function getTodayDashboard(deviceId?: string): Promise<DashboardResponse> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  const { data } = await api.get('/api/v1/dashboard/today', { params })
  return data
}

export async function getHistory(day: string, deviceId?: string): Promise<HistoryResponse> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  const { data } = await api.get(`/api/v1/history/${day}`, { params })
  return data
}

export async function getEditorContext(day: string, deviceId?: string, since?: string): Promise<EditorContextItem[]> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  if (since) params.since = since
  const { data } = await api.get(`/api/v1/context/editor/${day}`, { params })
  return data
}

export async function getBrowserContext(day: string, deviceId?: string, since?: string): Promise<BrowserContextItem[]> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  if (since) params.since = since
  const { data } = await api.get(`/api/v1/context/browser/${day}`, { params })
  return data
}

export async function getAppContext(day: string, deviceId?: string, since?: string): Promise<AppContextItem[]> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  if (since) params.since = since
  const { data } = await api.get(`/api/v1/context/app/${day}`, { params })
  return data
}

// --- Multi-User / Admin Management ---

export interface UserItem {
  id: number
  full_name: string
  email: string
  role: 'admin' | 'employee'
  registration_token: string
  created_at: string
  team_ids?: number[]
  monitoring_enabled?: boolean
}

export interface DeviceItem {
  id: number
  machine_guid: string
  os_type: string | null
  user_id: number | null
  email: string | null
  registered_at: string
  last_seen_at: string | null
}

export interface AdminStatus {
  is_setup: boolean
  admin_email: string | null
}

export async function getAdminStatus(): Promise<AdminStatus> {
  const { data } = await api.get('/api/v1/admin/status')
  return data
}

export async function setupAdmin(email: string): Promise<void> {
  await api.post('/api/v1/admin/setup', { email })
}

export async function listUsers(): Promise<UserItem[]> {
  const { data } = await api.get('/api/v1/admin/users')
  return data
}

export async function createUser(full_name: string, email: string): Promise<UserItem> {
  const { data } = await api.post('/api/v1/admin/users', { full_name, email })
  return data
}

export async function listDevices(): Promise<DeviceItem[]> {
  const { data } = await api.get('/api/v1/admin/devices')
  return data
}

export async function updateUserRole(email: string, role: string): Promise<void> {
  await api.put(`/api/v1/admin/users/${email}/role`, { role })
}

export async function updateUser(email: string, payload: { full_name?: string, email?: string, role?: string }): Promise<void> {
  await api.put(`/api/v1/admin/users/${email}`, payload)
}

export async function assignDevice(machine_guid: string, full_name: string, email: string, role: string): Promise<void> {
  await api.post(`/api/v1/admin/devices/${machine_guid}/assign`, { full_name, email, role })
}

export async function rejectDevice(machine_guid: string): Promise<void> {
  await api.post(`/api/v1/admin/devices/${machine_guid}/reject`)
}

export async function deleteUser(email: string): Promise<void> {
  await api.delete(`/api/v1/admin/users/${email}`)
}

export async function updateUserMonitoring(email: string, monitoring_enabled: boolean): Promise<void> {
  await api.put(`/api/v1/admin/users/${email}/monitoring`, { monitoring_enabled })
}

// --- Teams ---

export interface TeamItem {
  id: number
  name: string
  created_at: string
  created_by: string | null
}

export interface TeamMemberSummary {
  user_id: number
  full_name: string
  email: string
  machine_guid: string | null
  last_seen_at: string | null
  productivity_breakdown: ProductivityBreakdown
  total_minutes: number
  current_app_name: string | null
  current_window_title: string | null
  current_started_at: string | null
  current_ended_at: string | null
}

export interface TeamDashboardResponse {
  team_id: number
  team_name: string
  day: string
  aggregate: DashboardResponse
  members: TeamMemberSummary[]
}

export async function listTeams(): Promise<TeamItem[]> {
  const { data } = await api.get<TeamItem[]>('/api/v1/admin/teams')
  return data
}

export async function createTeam(name: string): Promise<TeamItem> {
  const { data } = await api.post<TeamItem>('/api/v1/admin/teams', { name })
  return data
}

export async function updateTeam(teamId: number, name: string): Promise<TeamItem> {
  const { data } = await api.patch<TeamItem>(`/api/v1/admin/teams/${teamId}`, { name })
  return data
}

export async function deleteTeam(teamId: number): Promise<void> {
  await api.delete(`/api/v1/admin/teams/${teamId}`)
}

export async function getTeamMembers(teamId: number): Promise<UserItem[]> {
  const { data } = await api.get<UserItem[]>(`/api/v1/admin/teams/${teamId}/members`)
  return data
}

export async function setTeamMembers(teamId: number, userIds: number[]): Promise<void> {
  await api.put(`/api/v1/admin/teams/${teamId}/members`, { user_ids: userIds })
}

export async function getTeamDashboard(teamId: number, day: string): Promise<TeamDashboardResponse> {
  const { data } = await api.get<TeamDashboardResponse>(`/api/v1/admin/teams/${teamId}/dashboard/${day}`)
  return data
}


export interface EditorContextItem {
  id: number
  captured_at: string
  editor_app: string
  workspace: string | null
  active_file: string | null
  active_file_path: string | null
  language: string | null
  open_files: string[]
  terminal_count: number
  git_branch: string | null
  debugger_active: boolean
}

export interface BrowserContextItem {
  id: number
  captured_at: string
  browser_app: string
  active_tab_url: string | null
  active_tab_title: string | null
  active_tab_domain: string | null
  tab_count: number
  open_domains: string[]
  youtube_video_title: string | null
  youtube_channel: string | null
  youtube_is_playing: boolean | null
  youtube_progress_pct: number | null
  productivity_label?: 'productive' | 'neutral' | 'distracting' | 'idle'
}

export interface AppContextItem {
  id: number
  captured_at: string
  app_name: string
  active_file_name: string | null
  active_file_path: string | null
  active_sequence: string | null
  notes: string | null
}
