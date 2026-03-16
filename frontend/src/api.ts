import axios from 'axios'
import type { DashboardResponse, HistoryResponse } from './types'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
})

export async function getDashboard(day: string): Promise<DashboardResponse> {
  const { data } = await api.get(`/api/v1/dashboard/${day}`)
  return data
}

export async function getTodayDashboard(): Promise<DashboardResponse> {
  const { data } = await api.get('/api/v1/dashboard/today')
  return data
}

export async function getHistory(day: string): Promise<HistoryResponse> {
  const { data } = await api.get(`/api/v1/history/${day}`)
  return data
}

export async function getEditorContext(day: string): Promise<EditorContextItem[]> {
  const { data } = await api.get(`/api/v1/context/editor/${day}`)
  return data
}

export async function getBrowserContext(day: string): Promise<BrowserContextItem[]> {
  const { data } = await api.get(`/api/v1/context/browser/${day}`)
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
