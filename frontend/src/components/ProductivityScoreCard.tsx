import React, { useMemo } from 'react'

interface ProductivityScoreProps {
  productivityPercentage: number // 0-100
  totalMinutes: number // total minutes tracked today
}

export default function ProductivityScoreCard({
  productivityPercentage,
  totalMinutes,
}: ProductivityScoreProps) {
  // Determine color based on percentage
  const getColor = (percentage: number) => {
    if (percentage >= 70) return '#10b981' // Green
    if (percentage >= 50) return '#eab308' // Yellow
    return '#ef4444' // Red
  }

  const color = getColor(productivityPercentage)
  const circumference = 2 * Math.PI * 85 // radius = 85
  const strokeDashoffset = circumference - (productivityPercentage / 100) * circumference

  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  const timeString = useMemo(() => {
    if (hours > 0) {
      return `${hours}h ${minutes}m`
    }
    return `${minutes}m`
  }, [hours, minutes])

  return (
    <div className="productivity-score">
      <svg width="200" height="200" viewBox="0 0 200 200">
        {/* Background circle */}
        <circle
          cx="100"
          cy="100"
          r="85"
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          opacity="0.1"
        />
        {/* Progress circle */}
        <circle
          cx="100"
          cy="100"
          r="85"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
      </svg>
      <p className="score-value">{productivityPercentage}%</p>
      <p className="score-label">Productivity Today • {timeString} tracked</p>
    </div>
  )
}
