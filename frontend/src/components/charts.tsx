import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Validated categorical slots (dataviz reference palette, light surface): slot 1 + slot 2.
export const SERIES_1 = '#2a78d6'
export const SERIES_2 = '#eb6834'
const AXIS = { stroke: '#94a3b8', fontSize: 12, tickLine: false, axisLine: false } as const
const GRID = '#e2e8f0'

const tooltipStyle = {
  contentStyle: { borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12, color: '#0f172a' },
  cursor: { fill: '#f1f5f9' },
}

/** Single-series horizontal bars (e.g. detections per category). Title names the series, so no legend. */
export function HBarChart({ data, label = 'Count', height }: { data: { name: string; value: number }[]; label?: string; height?: number }) {
  const h = height ?? Math.max(160, data.length * 34 + 30)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 32, bottom: 4, left: 8 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" allowDecimals={false} {...AXIS} />
        <YAxis type="category" dataKey="name" width={150} {...AXIS} tick={{ fill: '#334155', fontSize: 12 }} />
        <Tooltip {...tooltipStyle} formatter={(v) => [v, label]} />
        <Bar dataKey="value" name={label} fill={SERIES_1} radius={[0, 4, 4, 0]} maxBarSize={18}
          label={{ position: 'right', fill: '#475569', fontSize: 11 }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Two-series grouped comparison: FairClick agent vs manual baseline. Legend + tooltip; one y-axis. */
export function CompareChart({ data, agentLabel, manualLabel, unit = '' }:
  { data: { name: string; agent: number; manual: number }[]; agentLabel: string; manualLabel: string; unit?: string }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -8 }} barGap={2} barCategoryGap="22%">
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" {...AXIS} interval={0} height={78} angle={-35} textAnchor="end" tick={{ fill: '#334155', fontSize: 11 }} />
        <YAxis {...AXIS} unit={unit} />
        <Tooltip {...tooltipStyle} formatter={(v) => `${v}${unit}`} />
        <Legend iconType="square" wrapperStyle={{ fontSize: 12, color: '#334155' }} />
        <Bar dataKey="agent" name={agentLabel} fill={SERIES_1} radius={[4, 4, 0, 0]} maxBarSize={28} />
        <Bar dataKey="manual" name={manualLabel} fill={SERIES_2} radius={[4, 4, 0, 0]} maxBarSize={28} />
      </BarChart>
    </ResponsiveContainer>
  )
}
