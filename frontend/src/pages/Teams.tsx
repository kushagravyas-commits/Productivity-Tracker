import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  listTeams,
  createTeam,
  updateTeam,
  deleteTeam,
  listUsers,
  getTeamMembers,
  setTeamMembers,
  type TeamItem,
  type UserItem,
} from '../api'

interface TeamsProps {
  onViewDashboard: (team: TeamItem) => void
  isDarkMode: boolean
  onThemeToggle: () => void
}

export default function Teams({
  onViewDashboard,
  isDarkMode,
  onThemeToggle,
}: TeamsProps) {
  const [teams, setTeams] = useState<TeamItem[]>([])
  const [allUsers, setAllUsers] = useState<UserItem[]>([])
  const [newName, setNewName] = useState('')
  const [manageTeamId, setManageTeamId] = useState<number | null>(null)
  const [manageMemberIds, setManageMemberIds] = useState<number[]>([])
  const [renameTeamId, setRenameTeamId] = useState<number | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadLists = useCallback(async () => {
    try {
      setLoading(true)
      const [t, u] = await Promise.all([listTeams(), listUsers()])
      setTeams(t)
      setAllUsers(u)
    } catch (e) {
      console.error(e)
      setError('Could not load teams.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadLists()
  }, [loadLists])

  const teamMemberCount = useMemo(() => {
    const counts = new Map<number, number>()
    for (const u of allUsers) {
      const ids = u.team_ids ?? []
      for (const tid of ids) counts.set(tid, (counts.get(tid) ?? 0) + 1)
    }
    return counts
  }, [allUsers])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    try {
      setError('')
      await createTeam(newName.trim())
      setNewName('')
      await loadLists()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Could not create team')
    }
  }

  async function handleRename(e: React.FormEvent) {
    e.preventDefault()
    if (!renameTeamId || !renameValue.trim()) return
    try {
      setError('')
      await updateTeam(renameTeamId, renameValue.trim())
      setRenameTeamId(null)
      setRenameValue('')
      await loadLists()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Could not rename')
    }
  }

  async function handleDelete(teamId: number) {
    if (!confirm('Delete this team? Members will be unlinked from the team only.')) return
    try {
      await deleteTeam(teamId)
      await loadLists()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Could not delete')
    }
  }

  async function openManageMembers(teamId: number) {
    setManageTeamId(teamId)
    try {
      setError('')
      const members = await getTeamMembers(teamId)
      setManageMemberIds(members.map(m => m.id))
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Could not load team members')
    }
  }

  async function saveManageMembers() {
    if (!manageTeamId) return
    try {
      setError('')
      await setTeamMembers(manageTeamId, manageMemberIds)
      setManageTeamId(null)
      setManageMemberIds([])
      await loadLists()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Could not save members')
    }
  }

  function toggleManageMember(uid: number) {
    setManageMemberIds(prev => (prev.includes(uid) ? prev.filter(x => x !== uid) : [...prev, uid]))
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <div className="page-header-left">
          <div className="eyebrow">Admin Panel</div>
          <h1>Teams</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Create teams and view dashboards. Use “Manage members” to assign employees.
          </p>
        </div>
        <div className="page-header-right">
          <button
            className="btn-refresh"
            onClick={() => void loadLists()}
            title="Refresh"
            style={{ marginRight: 8 }}
          >
            ↻
          </button>
          <button
            className="btn btn-secondary"
            onClick={onThemeToggle}
            style={{ marginRight: 8 }}
            title="Toggle Theme"
          >
            {isDarkMode ? '☀️' : '🌙'}
          </button>
        </div>
      </div>

      {error && (
        <div className="notice" style={{ color: 'var(--red)', background: 'var(--red-bg)', border: '1px solid var(--border)', marginBottom: 16, padding: 12, borderRadius: 8 }}>
          {error}
        </div>
      )}

      <form onSubmit={handleCreate} className="card" style={{ marginBottom: 24, display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 200px' }}>
          <div className="date-label">New team name</div>
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder="e.g. Design"
            style={{ width: '100%' }}
          />
        </div>
        <button type="submit" className="btn btn-primary">Create team</button>
      </form>

      <div className="card" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <h2 style={{ fontSize: 18, margin: 0 }}>All Teams</h2>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Click “View Dashboard” to open a team’s page.
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading teams…
        </div>
      ) : teams.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          No teams yet.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          {teams.map(t => {
            const members = teamMemberCount.get(t.id) ?? 0
            return (
              <div key={t.id} className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 16 }}>{t.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                      Members: <strong>{members}</strong> · Created: <strong>{new Date(t.created_at).toLocaleDateString()}</strong>
                    </div>
                  </div>
                  <button className="btn btn-ghost" style={{ padding: '4px 10px' }} onClick={() => { setRenameTeamId(t.id); setRenameValue(t.name) }}>
                    Rename
                  </button>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                  <button className="btn btn-primary" onClick={() => onViewDashboard(t)}>
                    View Dashboard
                  </button>
                  <button className="btn btn-secondary" onClick={() => void openManageMembers(t.id)}>
                    Manage members
                  </button>
                  <button className="btn btn-ghost" style={{ color: 'var(--red)' }} onClick={() => void handleDelete(t.id)}>
                    Delete
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {renameTeamId && (
        <div className="modal-overlay">
          <div className="card modal-content" style={{ maxWidth: 420 }}>
            <h3 style={{ marginBottom: 12 }}>Rename team</h3>
            <form onSubmit={handleRename} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <div className="date-label">Team name</div>
                <input value={renameValue} onChange={e => setRenameValue(e.target.value)} style={{ width: '100%' }} />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>Save</button>
                <button type="button" className="btn btn-ghost" onClick={() => { setRenameTeamId(null); setRenameValue('') }}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {manageTeamId && (
        <div className="modal-overlay">
          <div className="card modal-content" style={{ maxWidth: 560 }}>
            <h3 style={{ marginBottom: 6 }}>Manage members</h3>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
              One employee can be in multiple teams.
            </p>
            <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 10, padding: 8 }}>
              {allUsers.map(u => (
                <label key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px', cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={manageMemberIds.includes(u.id)} onChange={() => toggleManageMember(u.id)} />
                  <span style={{ fontWeight: 600 }}>{u.full_name}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{u.email}</span>
                </label>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => void saveManageMembers()}>
                Save members
              </button>
              <button className="btn btn-ghost" onClick={() => { setManageTeamId(null); setManageMemberIds([]) }}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
