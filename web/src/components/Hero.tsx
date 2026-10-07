import { bucketTick, money, percent } from '../format'
import { seriesColor } from '../palette'
import type { Dashboard, RangeKey } from '../types'
import { ArrowDown, ArrowUp, CheckCircle, Stop, Warning } from './icons'

const SPAN: Record<RangeKey, string> = {
  '24h': 'spent in the last 24 hours',
  '7d': 'spent in the last 7 days',
  '30d': 'spent in the last 30 days',
  all: 'spent since the first request',
}

const PREVIOUS: Record<RangeKey, string> = {
  '24h': 'the previous 24 hours',
  '7d': 'the previous 7 days',
  '30d': 'the previous 30 days',
  all: '',
}

/** Turns the numbers into the one or two sentences someone would say out loud. */
function story(d: Dashboard): string[] {
  const { summary, by_model, by_feature } = d
  if (summary.requests > 0 && summary.cost <= 0) {
    return ['Costs show as $0 until each model has a price in pricing.json.']
  }
  if (summary.cost <= 0 || by_model.length === 0) return []

  const top = by_model[0]
  let first =
    by_model.length === 1
      ? `All of it went to ${top.model}`
      : `${top.model} accounts for ${percent(top.cost / summary.cost, 0)} of it`
  const tagged = by_feature.filter((f) => f.name !== '(untagged)')
  if (tagged.length >= 2) first += `, and ${tagged[0].name} is the costliest feature`

  const lines = [`${first}.`]
  const prev = summary.prev_cost
  if (prev && prev > 0 && PREVIOUS[d.range]) {
    const change = summary.cost / prev - 1
    if (Math.abs(change) < 0.0005) lines.push(`Level with ${PREVIOUS[d.range]}.`)
    else lines.push(`${change > 0 ? 'Up' : 'Down'} ${percent(Math.abs(change))} on ${PREVIOUS[d.range]}.`)
  }
  return lines
}

/** "$16,957.00" -> ["$16,957", ".00"] so the cents can be quieter than the dollars. */
function splitMoney(n: number): [string, string] {
  const text = money(n)
  const dot = text.indexOf('.')
  return dot === -1 ? [text, ''] : [text.slice(0, dot), text.slice(dot)]
}

export function Hero({ data }: { data: Dashboard }) {
  const lines = story(data)
  const [whole, fraction] = splitMoney(data.summary.cost)
  const prev = data.summary.prev_cost
  const change = prev && prev > 0 ? data.summary.cost / prev - 1 : null
  return (
    <section className="hero" aria-label="Spend summary">
      <div className="hero-main">
        <p className="hero-label">Total spend</p>
        <p className="hero-line">
          <span className="hero-figure">
            {whole}
            <span className="hero-cents">{fraction}</span>
          </span>
          {change !== null && Math.abs(change) >= 0.0005 && (
            <span className="delta" title={`Compared with ${PREVIOUS[data.range]}`}>
              {change > 0 ? <ArrowUp /> : <ArrowDown />}
              {percent(Math.abs(change), 1)}
            </span>
          )}
        </p>
        <p className="hero-span">{SPAN[data.range]}</p>
        {lines.map((line) => (
          <p className="hero-story" key={line}>
            {line}
          </p>
        ))}
        <Budget budget={data.budget} />
      </div>
      <ModelStrip data={data} />
    </section>
  )
}

/** Spend split by model: the top two models and everything else, each as wide as its share. */
function ModelStrip({ data }: { data: Dashboard }) {
  const total = data.summary.cost
  const models = data.by_model
  if (total <= 0 || models.length === 0) return <div />

  const slotOf = new Map(data.spend.series.map((s) => [s.key, s.slot]))
  const groups: { name: string; cost: number; color: string }[] = models.slice(0, 2).map((m) => ({
    name: m.model,
    cost: m.cost,
    color: seriesColor(slotOf.get(m.model) ?? null),
  }))
  const rest = models.slice(2)
  if (rest.length > 0) {
    groups.push({
      name: rest.length === 1 ? rest[0].model : `${rest.length} other models`,
      cost: rest.reduce((sum, m) => sum + m.cost, 0),
      color: 'var(--other)',
    })
  }

  const points = data.spend.points
  const perBucket = points.length > 0 ? total / points.length : total
  const first = points[0]?.t
  const last = points[points.length - 1]?.t

  return (
    <div className="strip" role="img" aria-label={`Spend by model: ${groups.map((g) => `${g.name} ${money(g.cost)}`).join(', ')}`}>
      <div className="strip-avg">
        <span>
          avg {money(perBucket)} / {data.bucket}
        </span>
      </div>
      <div className="strip-groups">
        {groups.map((g, i) => (
          <div className="strip-group" key={g.name} style={{ flexGrow: Math.max(g.cost / total, 0.14) * 100 }}>
            <p className="strip-value">{money(g.cost)}</p>
            <p className="strip-label">
              <strong>{percent(g.cost / total, 0)}</strong> {g.name}
            </p>
            <div
              className={i === 0 ? 'strip-bar solid' : i === 1 ? 'strip-bar ticks' : 'strip-bar ticks faint'}
              style={{ ['--bar' as string]: g.color }}
            />
          </div>
        ))}
      </div>
      {first && last && (
        <p className="strip-dates">
          <span>{bucketTick(first, 'day')}</span>
          <span>{bucketTick(last, 'day')}</span>
        </p>
      )}
    </div>
  )
}

function Budget({ budget }: { budget: Dashboard['budget'] }) {
  if (budget.limit === null) {
    return (
      <p className="budget-off">
        No daily budget set. Set <code>DAILY_BUDGET_USD</code> to track today&apos;s spend against a limit.
      </p>
    )
  }

  const share = budget.today / budget.limit
  const state = share >= 1 ? 'over' : share >= 0.8 ? 'close' : 'ok'
  const label = { over: 'Over budget', close: 'Close to the limit', ok: 'Within budget' }[state]
  const icon = { over: <Stop />, close: <Warning />, ok: <CheckCircle /> }[state]

  return (
    <div className="budget" data-state={state}>
      <p className="budget-amount">
        Today&apos;s budget: <strong>{money(budget.today)}</strong> of {money(budget.limit)}
      </p>
      <div
        className="meter"
        role="meter"
        aria-label="Spend today against the daily budget"
        aria-valuemin={0}
        aria-valuemax={budget.limit}
        aria-valuenow={budget.today}
      >
        <div className="meter-fill" style={{ width: `${Math.min(share, 1) * 100}%` }} />
      </div>
      <p className="budget-state">
        {icon}
        {label}. Counted by UTC day.
      </p>
    </div>
  )
}
