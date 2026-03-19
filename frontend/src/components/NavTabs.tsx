export type PageType = 'dashboard' | 'logs' | 'deep' | 'employees'

interface SidebarProps {
  currentPage: PageType
  onPageChange: (page: PageType) => void
  isDarkMode?: boolean
  onThemeToggle?: () => void
  day: string
  isLive: boolean
  isUserSelected: boolean
}

export default function Sidebar({
  currentPage,
  onPageChange,
  isDarkMode = false,
  onThemeToggle,
  day,
  isLive,
  isUserSelected
}: SidebarProps) {
  let navItems: { id: PageType; icon: string; label: string }[] = [
    { id: 'employees', icon: '👥', label: 'Team Members' },
  ]

  if (isUserSelected) {
    navItems = [
      { id: 'dashboard', icon: '⚡', label: 'Dashboard' },
      { id: 'logs', icon: '📋', label: 'Logs & Analytics' },
      { id: 'deep', icon: '🔬', label: 'Deep Activity' },
      { id: 'employees', icon: '👥', label: 'Back to Team' },
    ]
  }

  return (
    <nav className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">📊</div>
        <div>
          <div className="sidebar-logo-text">TrackFlow</div>
          <div className="sidebar-logo-sub">Productivity</div>
        </div>
      </div>

      {/* Navigation */}
      <div className="sidebar-nav">
        <div className="sidebar-nav-label">Pages</div>
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`sidebar-link ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onPageChange(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}

        <div style={{ marginTop: '24px' }}>
          <div className="sidebar-nav-label">Status</div>
          <div style={{ padding: '8px 12px' }}>
            {isLive ? (
              <span className="badge badge-live">Live</span>
            ) : (
              <span className="badge" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                Paused
              </span>
            )}
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
              {day}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        {onThemeToggle && (
          <button
            className="sidebar-link"
            onClick={onThemeToggle}
            title="Toggle theme"
          >
            <span className="nav-icon">{isDarkMode ? '☀️' : '🌙'}</span>
            <span>{isDarkMode ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        )}
      </div>
    </nav>
  )
}
