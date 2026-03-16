import { useEffect, useState } from 'react'
import './styles.css'
import { getDashboard, getEditorContext, getBrowserContext, getHistory, getTodayDashboard } from './api'
import type { EditorContextItem, BrowserContextItem } from './api'
import NavTabs, { type PageType } from './components/NavTabs'
import Dashboard from './pages/Dashboard'
import Logs from './pages/Logs'
import DeepActivity from './pages/DeepActivity'
import type { DashboardResponse, HistoryResponse } from './types'

const LIVE_REFRESH_MS = 5000

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
  const [currentPage, setCurrentPage] = useState<PageType>('dashboard')
  const [day, setDay] = useState(todayString())
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [weeklyBreakdowns, setWeeklyBreakdowns] = useState<WeeklyBreakdown[]>([])
  const [editorContext, setEditorContext] = useState<EditorContextItem[]>([])
  const [browserContext, setBrowserContext] = useState<BrowserContextItem[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [lastUpdated, setLastUpdated] = useState<string>('')
  const isToday = day === todayString()

  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme-preference')
    return saved ? saved === 'dark' : true
  })

  /** Fetch selected day + 6 preceding days in parallel. Selected day is always index 6 (rightmost). */
  async function loadWeekly(selectedDay: string) {
    // Build [day-6, day-5, ..., day-1, day]  (7 entries, selectedDay last)
    const days = Array.from({ length: 7 }, (_, i) => offsetDay(selectedDay, i - 6))
    try {
      const results = await Promise.allSettled(days.map(d => getDashboard(d)))
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
      // Silently fail — chart just shows zeros
    }
  }

  async function load(selectedDay: string, options?: { silent?: boolean }) {
    const silent = options?.silent ?? false
    if (!silent) setLoading(true)
    try {
      const [dash, hist] = await Promise.all([getDashboard(selectedDay), getHistory(selectedDay)])
      setDashboard(dash)
      setHistory(hist)
      setLastUpdated(new Date().toLocaleTimeString())
      if (!silent) setMessage('')
    } catch (error) {
      console.error(error)
      setMessage('Could not load data. Start the backend first.')
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

  // Load main + weekly + editor context whenever day changes
  useEffect(() => {
    void load(day)
    void loadWeekly(day)
    void getEditorContext(day).then(setEditorContext).catch(() => setEditorContext([]))
    void getBrowserContext(day).then(setBrowserContext).catch(() => setBrowserContext([]))
  }, [day])

  // Live refresh for today
  useEffect(() => {
    if (!isToday) return undefined
    const id = window.setInterval(() => {
      void load(day, { silent: true })
      void loadWeekly(day) // Refresh weekly trend too
      void getEditorContext(day).then(setEditorContext).catch(() => {})
      void getBrowserContext(day).then(setBrowserContext).catch(() => {})
    }, LIVE_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [day, isToday])

  async function handleLoadToday() {
    setLoading(true)
    try {
      const dash = await getTodayDashboard()
      setDay(dash.day)
      await load(dash.day)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <NavTabs
        currentPage={currentPage}
        onPageChange={setCurrentPage}
        isDarkMode={isDarkMode}
        onThemeToggle={() => setIsDarkMode(!isDarkMode)}
        day={day}
        isLive={isToday}
      />
      <div className="main-content">
        {currentPage === 'dashboard' ? (
          <Dashboard
            day={day}
            dashboard={dashboard}
            history={history}
            loading={loading}
            message={message}
            lastUpdated={lastUpdated}
            weeklyBreakdowns={weeklyBreakdowns}
            onDayChange={setDay}
            onLoadToday={handleLoadToday}
          />
        ) : currentPage === 'logs' ? (
          <Logs
            day={day}
            dashboard={dashboard}
            loading={loading}
            message={message}
            onDayChange={setDay}
            onLoadToday={handleLoadToday}
          />
        ) : (
          <DeepActivity
            day={day}
            editorContext={editorContext}
            browserContext={browserContext}
            onDayChange={setDay}
            onLoadToday={handleLoadToday}
          />
        )}
      </div>
    </div>
  )
}
