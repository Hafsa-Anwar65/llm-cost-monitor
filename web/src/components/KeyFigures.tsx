import { compact, duration, int, percent } from '../format'
import type { Summary } from '../types'

export function KeyFigures({ summary }: { summary: Summary }) {
  const items: [string, string][] = [
    ['Requests', int(summary.requests)],
    ['Input tokens', compact(summary.input_tokens)],
    ['Output tokens', compact(summary.output_tokens)],
    ['Median latency', duration(summary.p50)],
    ['Latency p95', duration(summary.p95)],
  ]
  if (summary.ttft_p50 !== null) items.push(['First token, median', duration(summary.ttft_p50)])
  items.push(['Failed requests', percent(summary.error_rate)])

  return (
    <dl className="figures">
      {items.map(([label, value]) => (
        <div className="figure" key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}
