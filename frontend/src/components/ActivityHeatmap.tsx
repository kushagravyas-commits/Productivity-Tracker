import { useMemo, useState } from 'react'
import { TimelineItem } from '../types'

interface ActivityHeatmapProps {
  items: TimelineItem[]
}

interface HeatmapCell {
  hour: number
  category: string
  minutes: number
}

export default function ActivityHeatmap({ items }: ActivityHeatmapProps) {
  const [hoveredCell, setHoveredCell] = useState<string | null>(null)

  const { data, maxMinutes } = useMemo(() => {
    const cells: HeatmapCell[] = []

    // Initialize all cells with 0
    for (let h = 0; h < 24; h++) {
      for (const cat of ['productive', 'neutral', 'distracting']) {
        cells.push({
          hour: h,
          category: cat,
          minutes: 0,
        })
      }
    }

    // Fill in actual data
    items.forEach((item) => {
      const startDate = new Date(item.started_at)
      const hour = startDate.getHours()
      const category = item.productivity_label || 'neutral'
      const endDate = new Date(item.ended_at)
      const minutes = Math.round((endDate.getTime() - startDate.getTime()) / 60000)

      const cellIdx = cells.findIndex((c) => c.hour === hour && c.category === category)
      if (cellIdx !== -1) {
        cells[cellIdx].minutes += minutes
      }
    })

    const max = Math.max(...cells.map((c) => c.minutes), 1)

    return { data: cells, maxMinutes: max }
  }, [items])

  const getIntensity = (minutes: number) => {
    if (minutes === 0) return 0.1
    return Math.min(1, minutes / maxMinutes)
  }

  const getCellColor = (category: string, intensity: number) => {
    const colorMap: Record<string, [number, number, number]> = {
      productive: [22, 101, 52], // green
      neutral: [7, 89, 133], // blue
      distracting: [153, 27, 27], // red
    }

    const [r, g, b] = colorMap[category] || [100, 100, 100]
    const alpha = intensity
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }

  const categories = ['productive', 'neutral', 'distracting']

  return (
    <div className="chart-wrap card">
      <h3>Activity Heatmap (Hour × Category)</h3>
      <div className="heatmap-container">
        <div className="heatmap">
          {/* Header */}
          <div style={{ display: 'contents' }}>
            <div className="heatmap-cell-header"></div>
            {categories.map((cat) => (
              <div key={cat} className="heatmap-cell-header">
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
              </div>
            ))}
          </div>

          {/* Cells */}
          {Array.from({ length: 24 }, (_, i) => i).map((hour) => (
            <div key={`row-${hour}`} style={{ display: 'contents' }}>
              <div className="heatmap-cell-label">
                {String(hour).padStart(2, '0')}:00
              </div>
              {categories.map((cat) => {
                const cell = data.find((c) => c.hour === hour && c.category === cat)
                const minutes = cell?.minutes || 0
                const intensity = getIntensity(minutes)
                const cellKey = `${hour}-${cat}`

                return (
                  <div
                    key={cellKey}
                    className="heatmap-cell"
                    style={{
                      backgroundColor: getCellColor(cat, intensity),
                      cursor: 'pointer',
                    }}
                    onMouseEnter={() => setHoveredCell(cellKey)}
                    onMouseLeave={() => setHoveredCell(null)}
                    title={`${String(hour).padStart(2, '0')}:00 - ${cat}: ${minutes}m`}
                  >
                    {hoveredCell === cellKey && minutes > 0 && (
                      <span className="heatmap-tooltip">{minutes}m</span>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
