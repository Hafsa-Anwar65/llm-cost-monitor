import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { bucketTick, bucketTitle, money, moneyAxis } from '../format'
import { usePrefersReducedMotion } from '../hooks'
import { seriesColor } from '../palette'
import type { SeriesDef, SpendPoint, Unit } from '../types'
import { DataTable, type Column } from './DataTable'
import { IconSpend } from './icons'
import { Section, ViewToggle, type View } from './Section'

interface TipProps {
  active?: boolean
  payload?: { name: string; value: number }[]
  label?: string
  unit: Unit
  colors: Record<string, string>
}

function SpendTip({ active, payload, label, unit, colors }: TipProps) {
  if (!active || !payload?.length || !label) return null
  const rows = payload.filter((p) => p.value > 0).sort((a, b) => b.value - a.value)
  if (!rows.length) return null
  const total = rows.reduce((sum, p) => sum + p.value, 0)
  return (
    <div className="tip">
      <p className="tip-title">{bucketTitle(label, unit)}</p>
      {rows.map((p) => (
        <p className="tip-row" key={p.name}>
          <span className="swatch" style={{ background: colors[p.name] }} />
          <span>{p.name}</span>
          <span>{money(p.value)}</span>
        </p>
      ))}
      {rows.length > 1 && (
        <p className="tip-total">
          <span>Total</span>
          <span>{money(total)}</span>
        </p>
      )}
    </div>
  )
}

export function SpendSection({ series, points, unit }: { series: SeriesDef[]; points: SpendPoint[]; unit: Unit }) {
  const [view, setView] = useState<View>('chart')
  const [hidden, setHidden] = useState<string[]>([])
  const reducedMotion = usePrefersReducedMotion()
  // The bars rise once when the page first loads; later refreshes just update in place.
  const [animate, setAnimate] = useState(!reducedMotion)
  useEffect(() => {
    const id = window.setTimeout(() => setAnimate(false), 1400)
    return () => window.clearTimeout(id)
  }, [])

  const colors = useMemo(
    () => Object.fromEntries(series.map((s) => [s.key, seriesColor(s.slot)])),
    [series],
  )
  // Recharts treats dots in a dataKey as a path, and model names contain dots ("gpt-4.1"),
  // so each series is addressed by position instead.
  const data = useMemo(
    () =>
      points.map((p) => ({
        t: p.t,
        ...Object.fromEntries(series.map((s, i) => [`k${i}`, p.values[s.key] ?? 0])),
      })),
    [points, series],
  )

  const total = points.reduce((sum, p) => sum + Object.values(p.values).reduce((a, b) => a + b, 0), 0)
  const note = `Each bar is one ${unit}, split by model.`

  const columns: Column<SpendPoint>[] = [
    { key: 't', header: unit === 'hour' ? 'Hour' : unit === 'week' ? 'Week of' : 'Day', value: (p) => p.t, render: (p) => bucketTitle(p.t, unit) },
    ...series.map((s) => ({
      key: s.key,
      header: s.key,
      numeric: true,
      value: (p: SpendPoint) => p.values[s.key] ?? 0,
      render: (p: SpendPoint) => money(p.values[s.key] ?? 0),
    })),
    {
      key: 'total',
      header: 'Total',
      numeric: true,
      value: (p) => Object.values(p.values).reduce((a, b) => a + b, 0),
      render: (p) => money(Object.values(p.values).reduce((a, b) => a + b, 0)),
    },
  ]

  return (
    <Section id="spend" className="span-2" icon={<IconSpend />} title="Spend over time" note={note} actions={<ViewToggle value={view} onChange={setView} />}>
      {total === 0 ? (
        <p className="empty-chart">No spend recorded in this range.</p>
      ) : view === 'table' ? (
        <DataTable rows={[...points].reverse()} columns={columns} caption="Spend per time bucket and model" />
      ) : (
        <>
          <div className="legend">
            {series.length > 1 &&
              series.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  className="legend-item"
                  aria-pressed={!hidden.includes(s.key)}
                  onClick={() => setHidden((h) => (h.includes(s.key) ? h.filter((k) => k !== s.key) : [...h, s.key]))}
                >
                  <span className="swatch" style={{ background: colors[s.key] }} />
                  {s.key}
                </button>
              ))}
          </div>
          <div className="chart" role="img" aria-label="Stacked column chart of spend over time by model. Use the table view for exact values.">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
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
                  tickFormatter={moneyAxis}
                  tickLine={false}
                  axisLine={false}
                  width={58}
                  tick={{ fill: 'var(--ink2)', fontSize: 12 }}
                />
                <Tooltip
                  cursor={{ fill: 'var(--hover)', radius: 6 }}
                  content={(p: any) => (
                    <SpendTip active={p.active} payload={p.payload} label={p.label} unit={unit} colors={colors} />
                  )}
                />
                {series.map(
                  (s, i) =>
                    !hidden.includes(s.key) && (
                      <Bar
                        key={s.key}
                        dataKey={`k${i}`}
                        name={s.key}
                        stackId="spend"
                        fill={colors[s.key]}
                        stroke="var(--surface)"
                        strokeWidth={2}
                        maxBarSize={26}
                        isAnimationActive={animate}
                      />
                    ),
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Section>
  )
}
