import { useState } from 'react'
import { setupAdmin } from '../api'

interface AdminActivationProps {
  onValidated: (email: string) => void
}

export default function AdminActivation({ onValidated }: AdminActivationProps) {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await setupAdmin(email)
      onValidated(email)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Activation failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ 
      height: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      background: 'var(--bg-base)',
      padding: 20
    }}>
      <div className="card" style={{ maxWidth: 450, width: '100%', padding: 40, textAlign: 'center' }}>
        <div style={{ fontSize: 40, marginBottom: 20 }}>🔐</div>
        <h1 style={{ marginBottom: 12 }}>Admin Activation</h1>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 32, fontSize: 14, lineHeight: 1.6 }}>
          This system is restricted. Please enter your authorized administrator email to activate the dashboard on this machine.
        </p>

        <form onSubmit={handleSubmit} style={{ textAlign: 'left' }}>
          <div style={{ marginBottom: 24 }}>
            <label className="date-label">Administrator Email</label>
            <input 
              type="email" 
              placeholder="name@varaheanalytics.com" 
              value={email}
              onChange={e => setEmail(e.target.value)}
              style={{ width: '100%', padding: '12px 16px', fontSize: 15 }}
              required
              autoFocus
            />
          </div>

          {error && (
            <div className="notice" style={{ 
              background: 'rgba(239, 68, 68, 0.1)', 
              color: 'var(--red-text)', 
              borderColor: 'var(--red)',
              marginBottom: 24 
            }}>
              {error}
            </div>
          )}

          <button 
            type="submit" 
            className="btn btn-primary" 
            style={{ width: '100%', padding: '14px', fontSize: 15, justifyContent: 'center' }}
            disabled={loading}
          >
            {loading ? 'Verifying...' : 'Activate Dashboard'}
          </button>
        </form>

        <div style={{ marginTop: 32, fontSize: 12, color: 'var(--text-muted)' }}>
          Only authorized emails from Varahe Analytics can perform this setup.
        </div>
      </div>
    </div>
  )
}
