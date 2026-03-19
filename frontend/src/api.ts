import axios from 'axios'
import type { DashboardResponse, HistoryResponse } from './types'

const baseURL = ''
const api = axios.create({
  baseURL,
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

export async function getEditorContext(day: string, deviceId?: string): Promise<EditorContextItem[]> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  const { data } = await api.get(`/api/v1/context/editor/${day}`, { params })
  return data
}

export async function getBrowserContext(day: string, deviceId?: string): Promise<BrowserContextItem[]> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
  const { data } = await api.get(`/api/v1/context/browser/${day}`, { params })
  return data
}

export async function getAppContext(day: string, deviceId?: string): Promise<AppContextItem[]> {
  const params: any = {}
  if (deviceId !== undefined) params.device_id = deviceId
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

export async function deleteUser(email: string): Promise<void> {
  await api.delete(`/api/v1/admin/users/${email}`)
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
