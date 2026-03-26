import { useEffect, useMemo, useState } from 'react'
import { listUsers, createUser, listDevices, listTeams, deleteUser, updateUserRole, updateUser, assignDevice, type UserItem, type DeviceItem, type TeamItem } from '../api'

interface UsersProps {
  onSelectUser: (machineGuid: string) => void
  isDarkMode: boolean
  onThemeToggle: () => void
}

export default function Users({ onSelectUser, isDarkMode, onThemeToggle }: UsersProps) {
  const [users, setUsers] = useState<UserItem[]>([])
  const [devices, setDevices] = useState<DeviceItem[]>([])
  const [teams, setTeams] = useState<TeamItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newRole, setNewRole] = useState<'admin' | 'employee'>('employee')
  const [error, setError] = useState('')
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState(false)
  const [showAssignModal, setShowAssignModal] = useState<{ machine_guid: string } | null>(null)
  const [editingCard, setEditingCard] = useState<string | null>(null) // email of user being edited
  const [teamFilter, setTeamFilter] = useState<'all' | 'no-team'>('all')

  const filteredUsers = useMemo(() => {
    if (teamFilter === 'no-team') {
      return users.filter(u => !u.team_ids || u.team_ids.length === 0)
    }
    return users
  }, [users, teamFilter])

  const teamIdToName = useMemo(() => {
    const m = new Map<number, string>()
    teams.forEach(t => m.set(t.id, t.name))
    return m
  }, [teams])

  async function loadData() {
    try {
      setLoading(true)
      const [u, d, t] = await Promise.all([listUsers(), listDevices(), listTeams().catch(() => [])])
      setUsers(u)
      setDevices(d)
      setTeams(t)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  async function handleAddUser(e: React.FormEvent) {
    e.preventDefault()
    if (!newName || !newEmail) return
    try {
      const user = await createUser(newName, newEmail)
      setCreatedToken(user.registration_token)
      setCopiedToken(false)
      setError('')
      await loadData()
    } catch (err: any) {
      console.error('Create user error:', err)
      setError(err.response?.data?.detail || err.message || 'Could not add user')
    }
  }

  function handleTokenDone() {
    setCreatedToken(null)
    setCopiedToken(false)
    setNewName('')
    setNewEmail('')
    setShowAddForm(false)
  }

  async function copyToken() {
    if (createdToken) {
      await navigator.clipboard.writeText(createdToken)
      setCopiedToken(true)
      setTimeout(() => setCopiedToken(false), 2000)
    }
  }

  async function handleRoleChange(email: string, role: string) {
    try {
      await updateUserRole(email, role)
      await loadData()
    } catch (err) {
      console.error(err)
      alert('Failed to update role')
    }
  }

  async function handleDelete(email: string) {
    if (!confirm(`Are you sure you want to delete ${email}?`)) return
    try {
      await deleteUser(email)
      await loadData()
    } catch (err) {
      console.error(err)
      alert('Failed to delete user')
    }
  }

  async function handleUpdateUser(originalEmail: string, updatedData: { full_name?: string, email?: string, role?: string }) {
    try {
      await updateUser(originalEmail, updatedData)
      setEditingCard(null)
      await loadData()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update user')
    }
  }

  async function handleAssignDevice(e: React.FormEvent) {
    e.preventDefault()
    if (!showAssignModal) return
    try {
      await assignDevice(showAssignModal.machine_guid, newName, newEmail, newRole)
      setNewName('')
      setNewEmail('')
      setNewRole('employee')
      setShowAssignModal(null)
      await loadData()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not assign device')
    }
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <div className="page-header-left">
          <div className="eyebrow">Admin Panel</div>
          <h1>Individual Employee Overview</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Monitor and manage your team members and their connected tracking devices.
          </p>
        </div>
        <div className="page-header-right">
          <button
            className="btn-refresh"
            onClick={loadData}
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
          <button
            className="btn btn-primary"
            onClick={() => setShowAddForm(!showAddForm)}
          >
            {showAddForm ? 'Cancel' : '+ Add Employee'}
          </button>
        </div>
      </div>

      {showAddForm && (
        <div className="card" style={{ marginBottom: 24, maxWidth: 400 }}>
          <h2 style={{ marginBottom: 16 }}>Add New Employee</h2>
          <form onSubmit={handleAddUser} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <div className="date-label">Full Name</div>
              <input 
                type="text" 
                placeholder="John Doe" 
                value={newName} 
                onChange={e => setNewName(e.target.value)}
                style={{ width: '100%' }}
                required
              />
            </div>
            <div>
              <div className="date-label">Email Address</div>
              <input 
                type="text" 
                placeholder="john@company.com" 
                value={newEmail} 
                onChange={e => setNewEmail(e.target.value)}
                style={{ width: '100%' }}
                required
              />
            </div>
            {error && <div className="notice" style={{ color: 'var(--red)', background: 'var(--red-bg)', border: '1px solid var(--border)' }}>{error}</div>}
            <button type="submit" className="btn btn-primary">Create User & Token</button>
          </form>
        </div>
      )}

      {createdToken && (
        <div className="modal-overlay">
          <div className="card modal-content" style={{ maxWidth: 440, textAlign: 'center' }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>🔑</div>
            <h3 style={{ marginBottom: 4 }}>Employee Created!</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
              Give this token to <strong>{newName}</strong> to enter when they first launch TrackFlow Agent on their machine.
            </p>
            <div style={{
              background: 'var(--bg-elevated)',
              border: '2px dashed var(--accent)',
              borderRadius: 12,
              padding: '16px 24px',
              marginBottom: 16,
              fontFamily: 'monospace',
              fontSize: 28,
              fontWeight: 700,
              letterSpacing: 4,
              color: 'var(--accent)'
            }}>
              {createdToken}
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button className="btn btn-primary" onClick={copyToken} style={{ minWidth: 140 }}>
                {copiedToken ? '✓ Copied!' : 'Copy Token'}
              </button>
              <button className="btn btn-ghost" onClick={handleTokenDone}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {showAssignModal && (
        <div className="modal-overlay">
          <div className="card modal-content" style={{ maxWidth: 400 }}>
            <h3>Assign Device: {showAssignModal.machine_guid.substring(0, 12)}...</h3>
            <form onSubmit={handleAssignDevice} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
              <div>
                <div className="date-label">Full Name</div>
                <input 
                  type="text" 
                  value={newName} 
                  onChange={e => setNewName(e.target.value)}
                  style={{ width: '100%' }}
                  placeholder="Employee Name"
                  required
                />
              </div>
              <div>
                <div className="date-label">Email Address</div>
                <input 
                  type="email" 
                  value={newEmail} 
                  onChange={e => setNewEmail(e.target.value)}
                  style={{ width: '100%' }}
                  placeholder="employee@varaheanalytics.com"
                  required
                />
              </div>
              <div>
                <div className="date-label">Role</div>
                <select 
                  value={newRole} 
                  onChange={e => setNewRole(e.target.value as any)}
                  style={{ width: '100%' }}
                >
                  <option value="employee">Employee</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              {error && <div className="notice" style={{ color: 'var(--red)' }}>{error}</div>}
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>Assign Now</button>
                <button type="button" className="btn btn-ghost" onClick={() => setShowAssignModal(null)}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div style={{ marginTop: 24, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Show:</span>
        <button
          type="button"
          className={`btn ${teamFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ padding: '4px 12px', fontSize: 12 }}
          onClick={() => setTeamFilter('all')}
        >
          All employees
        </button>
        <button
          type="button"
          className={`btn ${teamFilter === 'no-team' ? 'btn-primary' : 'btn-ghost'}`}
          style={{ padding: '4px 12px', fontSize: 12 }}
          onClick={() => setTeamFilter('no-team')}
        >
          Not in any team
        </button>
      </div>

      <div style={{ marginTop: 0 }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading team...</div>
        ) : users.length === 0 ? (
          <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No employees added yet.
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No employees match this filter.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 24 }}>
            {filteredUsers.map(u => {
              const userDevice = devices.find(d => d.email === u.email)
              const isEditing = editingCard === u.email
              const teamNames = (u.team_ids ?? []).map(id => teamIdToName.get(id)).filter(Boolean) as string[]
              
              return (
                <div key={u.email} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16, border: isEditing ? '2px solid var(--accent)' : '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                      <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), #7000ff)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
                        {u.full_name.charAt(0)}
                      </div>
                      <div style={{ flex: 1 }}>
                        {isEditing ? (
                          <input 
                            id={`edit-name-${u.email}`}
                            type="text" 
                            defaultValue={u.full_name} 
                            style={{ fontWeight: 600, fontSize: 16, background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 8px', width: '100%' }}
                          />
                        ) : (
                          <div style={{ fontWeight: 600, fontSize: 16 }}>{u.full_name}</div>
                        )}
                        <div className="badge" style={{ marginTop: 4, background: u.role === 'admin' ? 'rgba(0, 255, 127, 0.1)' : 'rgba(255, 255, 255, 0.05)', color: u.role === 'admin' ? '#00ffa3' : 'var(--text-secondary)', fontSize: 10 }}>
                          {u.role.toUpperCase()}
                        </div>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                          {teamNames.length > 0 ? (
                            teamNames.slice(0, 4).map((name) => (
                              <span
                                key={name}
                                className="badge"
                                style={{
                                  background: 'rgba(99, 102, 241, 0.12)',
                                  color: 'var(--text-secondary)',
                                  fontSize: 10,
                                }}
                                title={name}
                              >
                                {name}
                              </span>
                            ))
                          ) : (
                            <span
                              className="badge"
                              style={{
                                background: 'rgba(239, 68, 68, 0.12)',
                                color: 'var(--text-secondary)',
                                fontSize: 10,
                              }}
                              title="No team assigned"
                            >
                              Unassigned
                            </span>
                          )}
                          {teamNames.length > 4 && (
                            <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-muted)', fontSize: 10 }}>
                              +{teamNames.length - 4}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button 
                        className="btn btn-ghost" 
                        style={{ padding: '4px 8px', fontSize: 12 }}
                        onClick={() => {
                          if (isEditing) {
                            const nameInput = document.getElementById(`edit-name-${u.email}`) as HTMLInputElement
                            const emailInput = document.getElementById(`edit-email-${u.email}`) as HTMLInputElement
                            const roleSelect = document.getElementById(`edit-role-${u.email}`) as HTMLSelectElement
                            void handleUpdateUser(u.email, {
                              full_name: nameInput?.value || u.full_name,
                              email: emailInput?.value || u.email,
                              role: roleSelect?.value || (u.role as any)
                            })
                          } else {
                            setEditingCard(u.email)
                          }
                        }}
                      >
                        {isEditing ? 'Save' : 'Edit'}
                      </button>
                      {!isEditing && (
                        <button 
                          className="btn btn-ghost" 
                          style={{ padding: '4px 8px', fontSize: 12, color: 'var(--red)' }}
                          onClick={() => handleDelete(u.email)}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                      <span style={{ color: 'var(--text-muted)' }}>Email</span>
                      {isEditing ? (
                         <input 
                           id={`edit-email-${u.email}`}
                           type="email" 
                           defaultValue={u.email} 
                           style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 8px', width: '75%', fontSize: 11 }}
                         />
                      ) : (
                        <span style={{ color: 'var(--text-secondary)' }}>{u.email}</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                      <span style={{ color: 'var(--text-muted)' }}>Role</span>
                      {isEditing ? (
                        <select 
                          id={`edit-role-${u.email}`}
                          defaultValue={u.role} 
                          style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 8px', fontSize: 11 }}
                        >
                          <option value="employee">Employee</option>
                          <option value="admin">Admin</option>
                        </select>
                      ) : (
                        <span style={{ textTransform: 'capitalize' }}>{u.role}</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
                      <span style={{ color: 'var(--text-muted)' }}>Token</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <code style={{ fontSize: 11, color: 'var(--accent)', letterSpacing: 1 }}>{u.registration_token}</code>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '2px 6px', fontSize: 10, lineHeight: 1 }}
                          onClick={() => { void navigator.clipboard.writeText(u.registration_token); }}
                          title="Copy token"
                        >
                          📋
                        </button>
                      </div>
                    </div>
                    {userDevice && (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Machine GUID</span>
                          <code style={{ fontSize: 10, color: 'var(--accent)' }}>{userDevice.machine_guid.substring(0, 16)}...</code>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Last Seen</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{userDevice.last_seen_at ? new Date(userDevice.last_seen_at).toLocaleDateString() : 'Never'}</span>
                        </div>
                      </>
                    )}
                  </div>

                  <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                    {userDevice ? (
                      <button 
                        className="btn btn-primary" 
                        style={{ width: '100%', justifyContent: 'center' }}
                        onClick={() => onSelectUser(userDevice.machine_guid)}
                      >
                        View Tracking Dashboard
                      </button>
                    ) : (
                      <div style={{ textAlign: 'center', padding: '12px', background: 'var(--bg-elevated)', borderRadius: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                        Waiting for device assignment...
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div style={{ marginTop: 40 }}>
        <h2 style={{ fontSize: 18, marginBottom: 4 }}>Discovered Devices</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 16 }}>Newly connected machines waiting for assignment.</p>
        
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {devices.filter(d => !d.email).length === 0 ? (
            <div style={{ width: '100%', padding: 24, textAlign: 'center', background: 'var(--bg-surface)', borderRadius: 12, border: '1px dashed var(--border)', color: 'var(--text-muted)', fontSize: 13 }}>
              All detected devices are assigned.
            </div>
          ) : (
            devices.filter(d => !d.email).map(d => (
              <div key={d.machine_guid} className="card" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 16, minWidth: 320 }}>
                <div style={{ fontSize: 24 }}>{d.os_type === 'windows' ? '🪟' : '🍎'}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{d.machine_guid.substring(0, 16)}...</div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Status: Waiting for Assignment</div>
                </div>
                <button 
                  className="btn btn-primary" 
                  style={{ padding: '4px 12px', fontSize: 11 }}
                  onClick={() => {
                    setNewName('')
                    setNewEmail('')
                    setShowAssignModal({ machine_guid: d.machine_guid })
                  }}
                >
                  Assign User
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
