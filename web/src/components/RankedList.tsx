import { int, money } from '../format'
import type { Share } from '../types'
import type { ReactNode } from 'react'
import { Section } from './Section'

export function RankedList({
  id,
  title,
  icon,
  items,
  hint,
  color,
}: {
  id: string
  title: string
  icon: ReactNode
  items: Share[]
  hint: string
  color: string
}) {
  const max = Math.max(...items.map((i) => i.cost), 0)
  // One bar is not a comparison. Say how to get a breakdown instead.
  const comparable = items.length >= 2 && items.some((i) => i.name !== '(untagged)')

  return (
    <Section id={id} icon={icon} title={title} note="Top ten by cost">
      {comparable ? (
        <ol className="ranked">
          {items.map((item) => (
            <li key={item.name} title={`${int(item.requests)} requests`}>
              <span className="ranked-name">{item.name}</span>
              <span className="ranked-value">{money(item.cost)}</span>
              <span className="ranked-track">
                <span className="ranked-bar" style={{ width: `${max > 0 ? (item.cost / max) * 100 : 0}%`, background: color }} />
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="hint">{hint}</p>
      )}
    </Section>
  )
}
