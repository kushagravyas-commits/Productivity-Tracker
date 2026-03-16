import React from 'react'

interface QuickStatsCardProps {
  label: string
  value: string | number
  icon?: string
  trend?: 'up' | 'down'
}

export default function QuickStatsCard({ label, value, icon, trend }: QuickStatsCardProps) {
  return (
    <div className="quick-stat-card">
      {icon && <span style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>{icon}</span>}
      <p className="quick-stat-label">{label}</p>
      <p className="quick-stat-value">{value}</p>
      {trend && (
        <p className="quick-stat-trend">
          {trend === 'up' ? '📈 Up' : '📉 Down'} vs yesterday
        </p>
      )}
    </div>
  )
}
