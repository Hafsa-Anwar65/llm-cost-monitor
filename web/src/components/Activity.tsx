import type { Dashboard } from '../types'
import { int } from '../format'
import { IconActivity } from './icons'
import { Section } from './Section'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const FULL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const BLOCKS = ['12 am', '3 am', '6 am', '9 am', '12 pm', '3 pm', '6 pm', '9 pm']
const RANGE_LABEL = ['12 am to 3 am', '3 am to 6 am', '6 am to 9 am', '9 am to 12 pm', '12 pm to 3 pm', '3 pm to 6 pm', '6 pm to 9 pm', '9 pm to 12 am']

/** Requests by weekday and time of day. Colour steps are quartiles of the busiest cell. */
export function ActivityCard({ grid }: { grid: Dashboard['activity'] }) {
  const max = Math.max(...grid.flat(), 0)
  const level = (n: number) => (n <= 0 || max === 0 ? 0 : Math.min(4, Math.ceil((n / max) * 4)))

  let best = { d: 0, b: 0, n: 0 }
  grid.forEach((day, d) => day.forEach((n, b) => n > best.n && (best = { d, b, n })))

  return (
    <Section
      id="activity"
      icon={<IconActivity />}
      title="Activity by time"
      note={best.n > 0 ? `Busiest: ${FULL_DAYS[best.d]}, ${RANGE_LABEL[best.b]}` : 'No requests yet.'}
    >
      <div
        className="heat"
        role="img"
        aria-label={
          best.n > 0
            ? `Heatmap of requests by weekday and time of day. Busiest is ${FULL_DAYS[best.d]} from ${RANGE_LABEL[best.b]} with ${int(best.n)} requests.`
            : 'Heatmap of requests by weekday and time of day. No requests.'
        }
      >
        <span />
        {DAYS.map((d) => (
          <span className="heat-col" key={d}>
            {d}
          </span>
        ))}
        {BLOCKS.map((label, b) => (
          <div className="heat-row" key={label}>
            <span className="heat-time">{label}</span>
            {DAYS.map((d, di) => (
              <span
                key={d}
                className="heat-cell"
                data-level={level(grid[di]?.[b] ?? 0)}
                title={`${FULL_DAYS[di]}, ${RANGE_LABEL[b]}: ${int(grid[di]?.[b] ?? 0)} requests`}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="heat-legend" aria-hidden="true">
        <span>Less</span>
        {[0, 1, 2, 3, 4].map((l) => (
          <span key={l} className="heat-cell mini" data-level={l} />
        ))}
        <span>More</span>
      </div>
    </Section>
  )
}
