import type { KPI } from '../types'

type Props = {
  item: KPI
}

export function KpiCard({ item }: Props) {
  return (
    <div className="card kpi-card">
      <div className="muted">{item.label}</div>
      <div className="kpi-value">{item.display}</div>
    </div>
  )
}
