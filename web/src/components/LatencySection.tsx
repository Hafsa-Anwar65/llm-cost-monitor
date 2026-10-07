import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { bucketTick, bucketTitle, duration, durationAxis, money, percent } from '../format'
import type { LatencyPoint, ModelRow, Unit } from '../types'
import { DataTable, type Column } from './DataTable'
import { IconLatency, IconSpend } from './icons'
import { Section, ViewToggle, type View } from './Section'

const LINES = [
  { key: 'p50', label: 'Median (p50)', color: 'var(--s1)' },
  { key: 'p95', label: 'p95', color: 'var(--s2)' },
  { key: 'p99', label: 'p99', color: 'var(--s3)' },
] as const

type Key = (typeof LINES)[number]['key']

function LatencyTip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean
  payload?: { dataKey: Key; value: number | null }[]
  label?: string
  unit: Unit
}) {
  if (!active || !payload?.length || !label) return null
  return (
    <div className="tip">
      <p className="tip-title">{bucketTitle(label, unit)}</p>
      {LINES.map((l) => {
        const hit = payload.find((p) => p.dataKey === l.key)
        if (!hit || hit.value === null || hit.value === undefined) return null
        return (
          <p className="tip-row" key={l.key}>
            <span className="swatch swatch-line" style={{ background: l.color }} />
            <span>{l.label}</span>
            <span>{duration(hit.value)}</span>
          </p>
        )
      })}
    </div>
  )
}

export function LatencySection({
  points,
  unit,
}: {
  points: LatencyPoint[]
  unit: Unit
}) {
  const [view, setView] = useState<View>('chart')
  const hasData = points.some((p) => p.p50 !== null)

  // Marks the most recent bucket that has data, so each line ends in a dot.
  const lastIndex = useMemo(() => {
    const out: Record<Key, number> = { p50: -1, p95: -1, p99: -1 }
    points.forEach((p, i) => LINES.forEach((l) => p[l.key] !== null && (out[l.key] = i)))
    return out
  }, [points])

  const bucketColumns: Column<LatencyPoint>[] = [
    { key: 't', header: unit === 'hour' ? 'Hour' : unit === 'week' ? 'Week of' : 'Day', value: (p) => p.t, render: (p) => bucketTitle(p.t, unit) },
    { key: 'n', header: 'Successful requests', numeric: true, value: (p) => p.n },
    { key: 'p50', header: 'p50', numeric: true, value: (p) => p.p50, render: (p) => duration(p.p50) },
    { key: 'p95', header: 'p95', numeric: true, value: (p) => p.p95, render: (p) => duration(p.p95) },
    { key: 'p99', header: 'p99', numeric: true, value: (p) => p.p99, render: (p) => duration(p.p99) },
  ]

  return (
    <Section
      id="latency"
      className="span-2"
      icon={<IconLatency />}
      title="Latency"
      note="Percentiles of successful requests. Failed requests are left out so quick errors don't flatter the numbers."
      actions={<ViewToggle value={view} onChange={setView} />}
    >
      {!hasData ? (
        <p className="empty-chart">No successful requests in this range.</p>
      ) : view === 'table' ? (
        <DataTable rows={[...points].reverse()} columns={bucketColumns} caption="Latency percentiles per time bucket" />
      ) : (
        <>
          <div className="legend">
            {LINES.map((l) => (
              <span className="legend-item" key={l.key}>
                <span className="swatch swatch-line" style={{ background: l.color }} />
                {l.label}
              </span>
            ))}
          </div>
          <div className="chart" role="img" aria-label="Line chart of p50, p95 and p99 latency over time. Use the table view for exact values.">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis
                  dataKey="t"
                  tickFormatter={(t: string) => bucketTick(t, unit)}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--axis)' }}
                  tick={{ fill: 'var(--ink2)', fontSize: 12 }}
                  minTickGap={24}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tickFormatter={durationAxis}
                  tickLine={false}
                  axisLine={false}
                  width={58}
                  tick={{ fill: 'var(--ink2)', fontSize: 12 }}
                  domain={[0, 'auto']}
                />
                <Tooltip
                  cursor={{ stroke: 'var(--axis)' }}
                  content={(p: any) => <LatencyTip active={p.active} payload={p.payload} label={p.label} unit={unit} />}
                />
                {LINES.map((l) => (
                  <Line
                    key={l.key}
                    dataKey={l.key}
                    name={l.label}
                    type="linear"
                    stroke={l.color}
                    strokeWidth={2.5}
                    isAnimationActive={false}
                    connectNulls={false}
                    dot={(p: any) =>
                      p.index === lastIndex[l.key] && p.cx !== undefined && p.cy !== undefined ? (
                        <circle key={`${l.key}-end`} cx={p.cx} cy={p.cy} r={5} fill={l.color} stroke="var(--surface)" strokeWidth={2} />
                      ) : (
                        <g key={`${l.key}-${p.index}`} />
                      )
                    }
                    activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Section>
  )
}

export function ModelsCard({ models }: { models: ModelRow[] }) {
  const modelColumns: Column<ModelRow>[] = [
    { key: 'model', header: 'Model', value: (m) => m.model },
    { key: 'requests', header: 'Requests', numeric: true, value: (m) => m.requests },
    { key: 'cost', header: 'Cost', numeric: true, value: (m) => m.cost, render: (m) => money(m.cost) },
    { key: 'p50', header: 'p50', numeric: true, value: (m) => m.p50, render: (m) => duration(m.p50) },
    { key: 'p95', header: 'p95', numeric: true, value: (m) => m.p95, render: (m) => duration(m.p95) },
    { key: 'p99', header: 'p99', numeric: true, value: (m) => m.p99, render: (m) => duration(m.p99) },
    { key: 'ttft', header: 'First token', numeric: true, value: (m) => m.ttft_p50, render: (m) => duration(m.ttft_p50) },
    { key: 'err', header: 'Failed', numeric: true, value: (m) => m.error_rate, render: (m) => percent(m.error_rate) },
  ]

  return (
    <Section id="models" className="span-3" icon={<IconSpend />} title="By model" note="Cost and latency for each model in this range">
      <div className="table-wrap">
        <DataTable rows={models} columns={modelColumns} caption="Cost and latency per model" defaultSort={{ key: 'cost', dir: 'desc' }} />
      </div>
    </Section>
  )
}
