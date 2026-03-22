import { useEffect, useRef, useState } from 'react'
import './styles.css'
import {
  getDashboard, getEditorContext, getBrowserContext, getAppContext,
  getTodayDashboard, getAdminStatus
} from './api'
import type { EditorContextItem, BrowserContextItem, AppContextItem, AdminStatus } from './api'
import NavTabs, { type PageType } from './components/NavTabs'
import Dashboard from './pages/Dashboard'
import Logs from './pages/Logs'
import DeepActivity from './pages/DeepActivity'
import Users from './pages/Users'
import AdminActivation from './pages/AdminActivation'
import type { DashboardResponse } from './types'

const LIVE_REFRESH_MS = 15000

function todayString() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function offsetDay(baseDay: string, offsetDays: number): string {
  const d = new Date(baseDay + 'T00:00:00')
  d.setDate(d.getDate() + offsetDays)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export type WeeklyBreakdown = {
  date: string       // YYYY-MM-DD
  productive: number // minutes
  neutral: number
  distracting: number
  idle: number
}

export default function App() {
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null)
  const [currentPage, setCurrentPage] = useState<PageType>('employees')
  const [day, setDay] = useState(todayString())
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | undefined>(undefined)
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [weeklyBreakdowns, setWeeklyBreakdowns] = useState<WeeklyBreakdown[]>([])
  const [editorContext, setEditorContext] = useState<EditorContextItem[]>([])
  const [browserContext, setBrowserContext] = useState<BrowserContextItem[]>([])
  const [appContext, setAppContext] = useState<AppContextItem[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const [contextError, setContextError] = useState(false)
  const isToday = day === todayString()

  // Refs for incremental context fetching (track last timestamp per type)
  const lastEditorTs = useRef<string | null>(null)
  const lastBrowserTs = useRef<string | null>(null)
  const lastAppTs = useRef<string | null>(null)

  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme-preference')
    return saved ? saved === 'dark' : true
  })

  useEffect(() => {
    async function checkSetup() {
      try {
        const status = await getAdminStatus()
        setAdminStatus(status)
        if (status.is_setup) { /* devices fetched by Users page directly */ }
      } catch (err) {
        setAdminStatus({ is_setup: false, admin_email: null })
      }
    }
    checkSetup()
  }, [])

  /** Fetch selected day + 6 preceding days in parallel. Selected day is always index 6 (rightmost). */
  async function loadWeekly(selectedDay: string) {
    const days = Array.from({ length: 7 }, (_, i) => offsetDay(selectedDay, i - 6))
    try {
      const results = await Promise.allSettled(days.map(d => getDashboard(d, selectedDeviceId)))
      const breakdowns: WeeklyBreakdown[] = results.map((res, i) => {
        if (res.status === 'fulfilled') {
          const pb = res.value.productivity_breakdown
          return {
            date:        days[i],
            productive:  pb.productive  ?? 0,
            neutral:     pb.neutral     ?? 0,
            distracting: pb.distracting ?? 0,
            idle:        pb.idle        ?? 0,
          }
        }
        return { date: days[i], productive: 0, neutral: 0, distracting: 0, idle: 0 }
      })
      setWeeklyBreakdowns(breakdowns)
    } catch {
      // Silently fail
    }
  }

  async function load(selectedDay: string, options?: { silent?: boolean }) {
    if (!adminStatus?.is_setup) return

    const silent = options?.silent ?? false
    if (!silent) setLoading(true)
    try {
      const dash = await getDashboard(selectedDay, selectedDeviceId)
      setDashboard(dash)
      setLastUpdated(new Date().toLocaleTimeString())
      if (!silent) setMessage('')
    } catch (error) {
      console.error(error)
      setMessage('Data temporarily unavailable. Retrying...')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.remove('light-mode')
    } else {
      document.documentElement.classList.add('light-mode')
    }
    localStorage.setItem('theme-preference', isDarkMode ? 'dark' : 'light')
  }, [isDarkMode])

  useEffect(() => {
    if (!adminStatus?.is_setup) return

    // Safety: If no user selected, must stay on employees page
    if (selectedDeviceId === undefined && currentPage !== 'employees') {
      setCurrentPage('employees')
      return
    }

    // Skip heavy data fetching when on employees page (no device selected)
    if (currentPage === 'employees') return

    // Reset incremental refs on day/device change
    lastEditorTs.current = null
    lastBrowserTs.current = null
    lastAppTs.current = null
    setContextError(false)

    void load(day)
    void loadWeekly(day)
    void getEditorContext(day, selectedDeviceId).then(data => {
      setEditorContext(data)
      if (data.length > 0) lastEditorTs.current = data[data.length - 1].captured_at
      setContextError(false)
    }).catch(() => setContextError(true))
    void getBrowserContext(day, selectedDeviceId).then(data => {
      setBrowserContext(data)
      if (data.length > 0) lastBrowserTs.current = data[data.length - 1].captured_at
      setContextError(false)
    }).catch(() => setContextError(true))
    void getAppContext(day, selectedDeviceId).then(data => {
      setAppContext(data)
      if (data.length > 0) lastAppTs.current = data[data.length - 1].captured_at
      setContextError(false)
    }).catch(() => setContextError(true))
  }, [day, selectedDeviceId, adminStatus?.is_setup, currentPage])

  useEffect(() => {
    if (!isToday || !adminStatus?.is_setup || currentPage === 'employees') return undefined
    const id = window.setInterval(() => {
      void load(day, { silent: true })
      // Incremental context fetch — only get new snapshots since last fetch
      void getEditorContext(day, selectedDeviceId, lastEditorTs.current ?? undefined).then(data => {
        if (data.length > 0) {
          lastEditorTs.current = data[data.length - 1].captured_at
          setEditorContext(prev => [...prev, ...data])
        }
        setContextError(false)
      }).catch(() => setContextError(true))
      void getBrowserContext(day, selectedDeviceId, lastBrowserTs.current ?? undefined).then(data => {
        if (data.length > 0) {
          lastBrowserTs.current = data[data.length - 1].captured_at
          setBrowserContext(prev => [...prev, ...data])
        }
        setContextError(false)
      }).catch(() => setContextError(true))
      void getAppContext(day, selectedDeviceId, lastAppTs.current ?? undefined).then(data => {
        if (data.length > 0) {
          lastAppTs.current = data[data.length - 1].captured_at
          setAppContext(prev => [...prev, ...data])
        }
        setContextError(false)
      }).catch(() => setContextError(true))
    }, LIVE_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [day, isToday, selectedDeviceId, adminStatus?.is_setup, currentPage])

  async function handleLoadToday() {
    setLoading(true)
    try {
      const dash = await getTodayDashboard(selectedDeviceId)
      setDay(dash.day)
      await load(dash.day)
    } finally {
      setLoading(false)
    }
  }

  async function handleRefresh() {
    setLoading(true)
    // Reset incremental refs — force full reload
    lastEditorTs.current = null
    lastBrowserTs.current = null
    lastAppTs.current = null
    try {
      await Promise.all([
        load(day, { silent: true }),
        loadWeekly(day),
        getEditorContext(day, selectedDeviceId).then(data => {
          setEditorContext(data)
          if (data.length > 0) lastEditorTs.current = data[data.length - 1].captured_at
        }).catch(() => setContextError(true)),
        getBrowserContext(day, selectedDeviceId).then(data => {
          setBrowserContext(data)
          if (data.length > 0) lastBrowserTs.current = data[data.length - 1].captured_at
        }).catch(() => setContextError(true)),
        getAppContext(day, selectedDeviceId).then(data => {
          setAppContext(data)
          if (data.length > 0) lastAppTs.current = data[data.length - 1].captured_at
        }).catch(() => setContextError(true)),
      ])
      setLastUpdated(new Date().toLocaleTimeString())
    } finally {
      setLoading(false)
    }
  }

  // Handle successful admin activation
  if (adminStatus && !adminStatus.is_setup) {
    return (
      <AdminActivation 
        onValidated={(email) => {
          setAdminStatus({ is_setup: true, admin_email: email })
        }} 
      />
    )
  }

  if (!adminStatus) {
    return <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>Loading System...</div>
  }

  return (
    <div className="app-shell">
      {selectedDeviceId !== undefined && (
        <NavTabs
          currentPage={currentPage}
          onPageChange={(page) => {
            if (page === 'employees') {
              setSelectedDeviceId(undefined)
            }
            setCurrentPage(page)
          }}
          isDarkMode={isDarkMode}
          onThemeToggle={() => setIsDarkMode(!isDarkMode)}
          day={day}
          isLive={isToday}
          isUserSelected={selectedDeviceId !== undefined}
        />
      )}
      <div className="main-content">
        {/* Removed global Filter by Device dropdown since it's now drill-down based */}

        {currentPage === 'dashboard' ? (
          <Dashboard
            day={day}
            dashboard={dashboard}
            loading={loading}
            message={message}
            lastUpdated={lastUpdated}
            weeklyBreakdowns={weeklyBreakdowns}
            onDayChange={setDay}
            onLoadToday={handleLoadToday}
            onRefresh={handleRefresh}
          />
        ) : currentPage === 'logs' ? (
          <Logs
            day={day}
            dashboard={dashboard}
            loading={loading}
            message={message}
            onDayChange={setDay}
            onLoadToday={handleLoadToday}
            onRefresh={handleRefresh}
          />
        ) : currentPage === 'employees' ? (
          <Users 
            onSelectUser={(machineGuid) => {
              setSelectedDeviceId(machineGuid)
              setCurrentPage('dashboard')
            }} 
            isDarkMode={isDarkMode}
            onThemeToggle={() => setIsDarkMode(!isDarkMode)}
          />
        ) : (
          <DeepActivity
            day={day}
            editorContext={editorContext}
            browserContext={browserContext}
            appContext={appContext}
            loading={loading}
            contextError={contextError}
            onDayChange={setDay}
            onLoadToday={handleLoadToday}
            onRefresh={handleRefresh}
          />
        )}
      </div>
    </div>
  )
}
