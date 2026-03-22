import { useMemo, useState, useEffect } from 'react'
import type { EditorContextItem, BrowserContextItem, AppContextItem } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'

function todayString() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const LANG_COLORS: Record<string, string> = {
  python: '#3b82f6',
  typescript: '#8b5cf6',
  javascript: '#f59e0b',
  tsx: '#06b6d4',
  jsx: '#06b6d4',
  css: '#ec4899',
  html: '#f97316',
  json: '#84cc16',
  markdown: '#64748b',
  rust: '#f97316',
  go: '#22d3ee',
  java: '#ef4444',
  cpp: '#6366f1',
  c: '#6366f1',
  default: '#94a3b8',
}

function langColor(lang: string | null) {
  if (!lang) return LANG_COLORS.default
  return LANG_COLORS[lang.toLowerCase()] ?? LANG_COLORS.default
}

interface DeepActivityProps {
  day: string
  editorContext: EditorContextItem[]
  browserContext: BrowserContextItem[]
  appContext: AppContextItem[]
  loading?: boolean
  contextError?: boolean
  onDayChange: (day: string) => void
  onLoadToday: () => void
  onRefresh: () => void
}

type ActivityCategory = 'editor' | 'browser' | 'app'

export default function DeepActivity({ day, editorContext, browserContext, appContext, loading, contextError, onDayChange, onLoadToday, onRefresh }: DeepActivityProps) {
  const isToday = day === todayString()
  const [category, setCategory] = useState<ActivityCategory>('editor')
  const [userPickedCategory, setUserPickedCategory] = useState(false)
  const [selectedApp, setSelectedApp] = useState<string | null>(null)

  // Auto-select the best tab once data first arrives, but only if user hasn't clicked a tab yet
  useEffect(() => {
    if (userPickedCategory) return
    if (appContext.length > 0) setCategory('app')
    else if (editorContext.length > 0) setCategory('editor')
    else if (browserContext.length > 0) setCategory('browser')
  }, [editorContext.length, browserContext.length, appContext.length, userPickedCategory])

  // --- EDITOR DATA PROCESSING ---
  const editorApps = useMemo(() => Array.from(new Set(editorContext.map(e => e.editor_app))), [editorContext])
  const activeEditorApp = selectedApp ?? editorApps[0] ?? null
  const appEditorData = useMemo(() => editorContext.filter(e => e.editor_app === activeEditorApp), [editorContext, activeEditorApp])

  const fileFreq = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const snap of appEditorData) {
      if (snap.active_file) counts[snap.active_file] = (counts[snap.active_file] ?? 0) + 1
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([file, count]) => ({ file, seconds: count * 5 }))
  }, [appEditorData])

  const langData = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const snap of appEditorData) {
      if (!snap.language) continue
      const l = snap.language
      counts[l] = (counts[l] ?? 0) + 1
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([lang, count]) => ({ name: lang, value: count * 5, color: langColor(lang) }))
  }, [appEditorData])

  const editorSummary = useMemo(() => {
    if (!appEditorData.length) return null
    const snap = appEditorData[appEditorData.length - 1]
    return {
      workspace: snap.workspace,
      gitBranch: snap.git_branch,
      maxTerminals: Math.max(...appEditorData.map(e => e.terminal_count)),
      debugSessions: appEditorData.filter(e => e.debugger_active).length,
      totalSnaps: appEditorData.length
    }
  }, [appEditorData])

  // --- BROWSER DATA PROCESSING ---
  const browserApps = useMemo(() => Array.from(new Set(browserContext.map(b => b.browser_app))), [browserContext])
  const activeBrowserApp = selectedApp ?? browserApps[0] ?? null
  const browserData = useMemo(() => browserContext.filter(b => b.browser_app === activeBrowserApp), [browserContext, activeBrowserApp])

  const domainFreq = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const snap of browserData) {
      if (snap.active_tab_domain) counts[snap.active_tab_domain] = (counts[snap.active_tab_domain] ?? 0) + 1
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([domain, count]) => ({ domain, seconds: count * 5 }))
  }, [browserData])

  const browserProductivity = useMemo(() => {
    const counts: Record<string, number> = { productive: 0, neutral: 0, distracting: 0 }
    for (const snap of browserData) {
      const label = snap.productivity_label || 'neutral'
      counts[label] = (counts[label] ?? 0) + 5
    }
    return Object.entries(counts).map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value,
      color: name === 'productive' ? 'var(--green)' : name === 'distracting' ? 'var(--red)' : 'var(--blue)'
    })).filter(c => c.value > 0)
  }, [browserData])

  const browserTimeline = useMemo(() => {
    const segments: { title: string; domain: string | null; start: string; end: string; count: number; label: string }[] = []
    for (const snap of browserData) {
      const last = segments[segments.length - 1]
      const currentTitle = snap.active_tab_title ?? '—'
      const currentLabel = snap.productivity_label || 'neutral'
      if (last && last.title === currentTitle && last.label === currentLabel) {
        last.end = snap.captured_at
        last.count++
      } else {
        segments.push({ title: currentTitle, domain: snap.active_tab_domain, start: snap.captured_at, end: snap.captured_at, count: 1, label: currentLabel })
      }
    }
    return segments.reverse()
  }, [browserData])

  const browserSummary = useMemo(() => {
    if (!browserData.length) return null
    const totalTabs = Math.max(...browserData.map(b => b.tab_count))
    const uniqueDomains = new Set(browserData.flatMap(b => b.open_domains)).size
    const ytVideos = new Set(browserData.map(b => b.youtube_video_title).filter(Boolean)).size
    return { totalTabs, uniqueDomains, ytVideos, totalSnaps: browserData.length }
  }, [browserData])

  // --- APP (ADOBE/DAVINCI) DATA PROCESSING ---
  const genericApps = useMemo(() => Array.from(new Set(appContext.map(a => a.app_name))), [appContext])
  const activeGenericApp = selectedApp ?? genericApps[0] ?? null
  const genericAppData = useMemo(() => appContext.filter(a => a.app_name === activeGenericApp), [appContext, activeGenericApp])

  const genericFileFreq = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const snap of genericAppData) {
      const key = snap.active_file_name || snap.active_file_path || 'Untitled'
      counts[key] = (counts[key] ?? 0) + 1
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([file, count]) => ({ file, seconds: count * 5 }))
  }, [genericAppData])

  const genericTimeline = useMemo(() => {
    const segments: { file: string; sequence: string | null; start: string; end: string; count: number }[] = []
    for (const snap of genericAppData) {
      const last = segments[segments.length - 1]
      const currentFile = snap.active_file_name || snap.active_file_path || 'Untitled'
      const currentSeq = snap.active_sequence
      if (last && last.file === currentFile && last.sequence === currentSeq) {
        last.end = snap.captured_at
        last.count++
      } else {
        segments.push({ file: currentFile, sequence: currentSeq, start: snap.captured_at, end: snap.captured_at, count: 1 })
      }
    }
    return segments.reverse()
  }, [genericAppData])

  const genericSummary = useMemo(() => {
    if (!genericAppData.length) return null
    const totalSnaps = genericAppData.length
    const uniqueFiles = new Set(genericAppData.map(a => a.active_file_path).filter(Boolean)).size
    return { totalSnaps, uniqueFiles }
  }, [genericAppData])

  const hasData = (
    category === 'editor' ? appEditorData.length :
    category === 'browser' ? browserData.length :
    genericAppData.length
  ) > 0

  const navApps = category === 'editor' ? editorApps : category === 'browser' ? browserApps : genericApps
  const activeApp = category === 'editor' ? activeEditorApp : category === 'browser' ? activeBrowserApp : activeGenericApp

  return (
    <div className="page-shell">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <div className="eyebrow">Deep Activity Intelligence</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <h1>Deep Activity 🔬</h1>
            <div style={{ display: 'flex', background: 'var(--bg-elevated)', borderRadius: 12, padding: 4 }}>
              <button
                className={`tab-btn ${category === 'editor' ? 'active' : ''}`}
                onClick={() => { setCategory('editor'); setSelectedApp(null); setUserPickedCategory(true); }}
              >
                💻 Editor
              </button>
              <button
                className={`tab-btn ${category === 'browser' ? 'active' : ''}`}
                onClick={() => { setCategory('browser'); setSelectedApp(null); setUserPickedCategory(true); }}
              >
                🌐 Browser
              </button>
              <button
                className={`tab-btn ${category === 'app' ? 'active' : ''}`}
                onClick={() => { setCategory('app'); setSelectedApp(null); setUserPickedCategory(true); }}
              >
                🎨 App
              </button>
            </div>
          </div>
        </div>
        <div className="page-header-right">
          {isToday && <span className="badge badge-live">Live</span>}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="date" value={day} onChange={e => onDayChange(e.target.value)} className="date-input" />
            {!isToday && <button className="btn-primary" onClick={onLoadToday}>Today</button>}
            <button className="btn-refresh" onClick={onRefresh} disabled={loading} title="Refresh data" style={loading ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}>↻</button>
          </div>
        </div>
      </div>

      {/* App pills */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {navApps.map(app => (
          <button
            key={app}
            onClick={() => setSelectedApp(app)}
            className={`pill-btn ${activeApp === app ? 'active' : ''}`}
          >
            {
              app.includes('Photoshop') ? '🖌️' :
              app.includes('Premiere') ? '🎬' :
              app.includes('After Effects') ? '🧪' :
              app.includes('Illustrator') ? '📐' :
              app.includes('Resolve') ? '🎥' :
              app === 'Antigravity' ? '🚀' :
              app === 'VS Code' ? '💻' :
              app === 'Chrome' ? '🌐' :
              app === 'Brave' ? '🦁' : '🖥️'
            } {app}
          </button>
        ))}
      </div>

      {contextError && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '10px 16px', marginBottom: 16, fontSize: 13, color: 'var(--text-primary)' }}>
          Unable to fetch latest deep activity data. Retrying automatically...
        </div>
      )}

      {!hasData ? (
        <div className="notice notice-info" style={{ marginTop: 40, textAlign: 'center', padding: '60px 24px' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔌</div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>No {category} data for this day</div>
        </div>
      ) : category === 'editor' ? (
        /* --- EDITOR VIEW --- */
        <>
          {editorSummary && (
            <div className="card grid-5" style={{ marginBottom: 24 }}>
              <Kpi label="Workspace" value={editorSummary.workspace ?? '—'} />
              <Kpi label="Git Branch" value={editorSummary.gitBranch ? `⎇ ${editorSummary.gitBranch}` : '—'} />
              <Kpi label="Max Terminals" value={editorSummary.maxTerminals} />
              <Kpi label="Debug Sessions" value={editorSummary.debugSessions} color={editorSummary.debugSessions > 0 ? 'var(--accent)' : undefined} icon={editorSummary.debugSessions > 0 ? '🐛' : undefined} />
              <Kpi label="Tracked Time" value={`${Math.round(editorSummary.totalSnaps * 5 / 60)}m`} />
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr', gap: 20, marginBottom: 24 }}>
            <Card title="📁 Most Edited Files" icon="folder">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={fileFreq} layout="vertical" margin={{ left: 8, right: 20 }}>
                  <XAxis type="number" tickFormatter={v => v >= 60 ? `${Math.round(v / 60)}m` : `${v}s`} hide />
                  <YAxis type="category" dataKey="file" width={120} tick={{ fontSize: 11 }} tickFormatter={v => v.length > 18 ? `…${v.slice(-16)}` : v} />
                  <Tooltip formatter={(v: number) => [v >= 60 ? `${Math.round(v / 60)}m` : `${v}s`, 'Time']} />
                  <Bar dataKey="seconds" fill="var(--accent)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="🌐 Language Breakdown" icon="code">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={langData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={90}>
                    {langData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Legend />
                  <Tooltip formatter={(v: number) => [`${Math.round(v / 60)}m`, 'Time']} />
                </PieChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <Card title="📋 Snapshot Log">
            <div className="table-container">
              <table>
                <thead>
                  <tr>{['Time', 'File', 'Lang', 'Tabs', 'Term', 'Branch', 'Debug'].map(h => <th key={h}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {appEditorData.slice(-50).reverse().map((snap, i) => (
                    <tr key={snap.captured_at + i}>
                      <td>{fmtTime(snap.captured_at)}</td>
                      <td style={{ fontWeight: 500 }}>{snap.active_file ?? '—'}</td>
                      <td>{snap.language && <span className="lang-badge" style={{ background: langColor(snap.language) + '22', color: langColor(snap.language) }}>{snap.language}</span>}</td>
                      <td>{snap.open_files.length}</td>
                      <td>{snap.terminal_count}</td>
                      <td>{snap.git_branch ? `⎇ ${snap.git_branch}` : '—'}</td>
                      <td>{snap.debugger_active ? '🐛 Active' : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : category === 'browser' ? (
        /* --- BROWSER VIEW --- */
        <>
          {browserSummary && (
            <div className="card grid-4" style={{ marginBottom: 24 }}>
              <Kpi label="Max Tabs" value={browserSummary.totalTabs} />
              <Kpi label="Unique Domains" value={browserSummary.uniqueDomains} />
              <Kpi label="YT Videos" value={browserSummary.ytVideos} icon="🎬" />
              <Kpi label="Browsing Time" value={`${Math.round(browserSummary.totalSnaps * 5 / 60)}m`} />
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr', gap: 20, marginBottom: 24 }}>
            <Card title="🌐 Most Visited Domains" icon="globe" style={{ minWidth: 0 }}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={domainFreq} layout="vertical" margin={{ left: 8, right: 20 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="domain" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => [`${Math.round(v / 60)}m`, 'Time']} />
                  <Bar dataKey="seconds" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="📊 Productivity Distribution" icon="code" style={{ minWidth: 0 }}>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={browserProductivity} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={90}>
                    {browserProductivity.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip formatter={(v: number) => [`${Math.round(v / 60)}m`, 'Time']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <Card title="⏱️ Browsing Timeline" style={{ marginBottom: 24 }}>
            <div className="timeline-list">
              {browserTimeline.map((seg, i) => (
                <div key={i} className="timeline-row">
                  <span className="time">{fmtTime(seg.start)}</span>
                  <div className="content">
                    <div className="lang-indicator" style={{ background: seg.label === 'productive' ? 'var(--green)' : seg.label === 'distracting' ? 'var(--red)' : 'var(--blue)' }} />
                    <div style={{ overflow: 'hidden' }}>
                      <span className="sub" style={{ fontSize: 10, textTransform: 'uppercase' }}>{seg.domain ?? 'internal'}</span>
                      <span className="title">{seg.title}</span>
                    </div>
                  </div>
                  <span className="duration">{seg.count * 5 >= 60 ? `${Math.round(seg.count * 5 / 60)}m` : `${seg.count * 5}s`}</span>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : (
        /* --- GENERIC APP VIEW --- */
        <>
          {genericSummary && (
            <div className="card grid-3" style={{ marginBottom: 24 }}>
              <Kpi label="Active Project Count" value={genericSummary.uniqueFiles} />
              <Kpi label="Total Snapshots" value={genericSummary.totalSnaps} />
              <Kpi label="Estimated Active Time" value={`${Math.round(genericSummary.totalSnaps * 5 / 60)}m`} />
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr', gap: 20, marginBottom: 24 }}>
            <Card title="📂 Most Active Projects" icon="folder" style={{ minWidth: 0 }}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={genericFileFreq} layout="vertical" margin={{ left: 8, right: 20 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="file" width={140} tick={{ fontSize: 11 }} tickFormatter={v => v.length > 20 ? `…${v.slice(-18)}` : v} />
                  <Tooltip formatter={(v: number) => [`${Math.round(v / 60)}m`, 'Time']} />
                  <Bar dataKey="seconds" fill="var(--accent)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="⏱️ App Activity Timeline" icon="globe" style={{ minWidth: 0 }}>
               <div className="timeline-list">
              {genericTimeline.map((seg, i) => (
                <div key={i} className="timeline-row">
                  <span className="time">{fmtTime(seg.start)}</span>
                  <div className="content">
                    <div className="lang-indicator" style={{ background: 'var(--accent)' }} />
                    <div style={{ overflow: 'hidden' }}>
                      <span className="sub" style={{ fontSize: 10, textTransform: 'uppercase' }}>{seg.sequence ? `Sequence: ${seg.sequence}` : 'Project'}</span>
                      <span className="title">{seg.file}</span>
                    </div>
                  </div>
                  <span className="duration">{seg.count * 5 >= 60 ? `${Math.round(seg.count * 5 / 60)}m` : `${seg.count * 5}s`}</span>
                </div>
              ))}
            </div>
            </Card>
          </div>

          <Card title="📋 Insight Log">
            <div className="table-container">
              <table>
                <thead>
                  <tr>{['Time', 'App', 'Project / File', 'Sequence', 'Notes'].map(h => <th key={h}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {genericAppData.slice(-50).reverse().map(snap => (
                    <tr key={snap.id}>
                      <td>{fmtTime(snap.captured_at)}</td>
                      <td style={{ fontWeight: 500 }}>{snap.app_name}</td>
                      <td>{snap.active_file_name || snap.active_file_path || '—'}</td>
                      <td>{snap.active_sequence || '—'}</td>
                      <td>{snap.notes || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <style>{`
        .tab-btn {
          padding: 8px 16px; border: none; background: transparent; color: var(--text-muted);
          cursor: pointer; font-size: 14; font-weight: 500; border-radius: 8px; transition: all 0.2s;
        }
        .tab-btn.active { background: var(--bg-card); color: var(--text-primary); box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
        .pill-btn {
          padding: 8px 20px; border-radius: 999px; cursor: pointer; font-size: 14px; transition: all 0.15s;
          background: var(--bg-card); border: 1.5px solid var(--border); color: var(--text-primary);
        }
        .pill-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
        .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
        .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
        .grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; }
        .timeline-list { display: flex; flex-direction: column; gap: 6px; max-height: 400px; overflow-y: auto; }
        .timeline-list.small { max-height: 260px; }
        .timeline-row {
          display: grid; grid-template-columns: 80px 1fr auto; align-items: center; gap: 12px;
          padding: 8px 12px; border-radius: 8px; background: var(--bg-elevated);
        }
        .timeline-row .time { font-size: 11px; color: var(--text-muted); }
        .timeline-row .content { display: flex; align-items: center; gap: 8px; overflow: hidden; }
        .timeline-row .lang-indicator { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .timeline-row .title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .timeline-row .duration { fontSize: 12px; color: var(--text-muted); }
        .timeline-row .sub { font-size: 11px; color: var(--text-muted); display: block; }
        .table-container { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; fontSize: 13px; }
        th { padding: 12px; text-align: left; color: var(--text-muted); font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--border); }
        td { padding: 12px; border-bottom: 1px solid var(--border); }
        .lang-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
      `}</style>
    </div>
  )
}

function Kpi({ label, value, color, icon }: { label: string; value: any; color?: string; icon?: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontWeight: 600, fontSize: 16, color }}>{icon && <span style={{ marginRight: 6 }}>{icon}</span>}{value}</div>
    </div>
  )
}

function Card({ title, icon, children, style }: { title: string; icon?: string; children: any; style?: any }) {
  return (
    <div className="card" style={style}>
      <div className="card-header">
        <span className="card-title">{icon === 'folder' ? '📁' : icon === 'code' ? '🌐' : icon === 'globe' ? '🌐' : icon === 'play' ? '🎬' : ''} {title}</span>
      </div>
      {children}
    </div>
  )
}
