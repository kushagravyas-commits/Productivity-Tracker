import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'
import type { DashboardResponse } from '../types'

interface WeeklyComparisonProps {
  currentDayData: DashboardResponse | null
  currentDay: string
}

export default function WeeklyComparisonChart({
  currentDayData,
  currentDay,
}: WeeklyComparisonProps) {
  // Create 7-day data array with placeholder data
  const sevenDayData = useMemo(() => {
    const data: { day: string; percentage: number }[] = []

    // Get last 7 days
    for (let i = 6; i >= 0; i--) {
      const date = new Date(currentDay)
      date.setDate(date.getDate() - i)
      const dayOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][date.getDay()]

      if (i === 0 && currentDayData) {
        // For today, use actual data
        const productive = currentDayData.productivity_breakdown?.productive || 0
        const total =
          (currentDayData.productivity_breakdown?.productive || 0) +
          (currentDayData.productivity_breakdown?.neutral || 0) +
          (currentDayData.productivity_breakdown?.distracting || 0) +
          (currentDayData.productivity_breakdown?.idle || 0)
        const percentage = total > 0 ? Math.round((productive / total) * 100) : 0

        data.push({
          day: dayOfWeek,
          percentage,
        })
      } else {
        // For other days, show placeholder
        data.push({
          day: dayOfWeek,
          percentage: 0,
        })
      }
    }

    return data
  }, [currentDayData, currentDay])

  return (
    <div className="weekly-chart">
      <h3>Weekly Productivity Trend</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={sevenDayData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
          <XAxis dataKey="day" stroke="var(--text-secondary)" />
          <YAxis domain={[0, 100]} stroke="var(--text-secondary)" />
          <Tooltip
            contentStyle={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
            }}
            formatter={(value: number) => `${value}%`}
          />
          <Line
            type="monotone"
            dataKey="percentage"
            stroke="#10b981"
            strokeWidth={3}
            dot={{ fill: '#10b981', r: 5 }}
            activeDot={{ r: 7 }}
            isAnimationActive={true}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
