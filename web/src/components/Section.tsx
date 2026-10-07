import type { ReactNode } from 'react'

export type View = 'chart' | 'table'

export function Section({
  id,
  title,
  note,
  icon,
  actions,
  className = '',
  children,
}: {
  id?: string
  title: string
  note?: string
  icon?: ReactNode
  actions?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={`card ${className}`.trim()} id={id} aria-labelledby={id ? `${id}-title` : undefined}>
      <header className="card-head">
        <div className="card-title">
          {icon && <span className="card-icon">{icon}</span>}
          <div>
            <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
            {note && <p className="card-note">{note}</p>}
          </div>
        </div>
        {actions && <div className="card-actions">{actions}</div>}
      </header>
      {children}
    </section>
  )
}

export function ViewToggle({
  value,
  onChange,
  labels = ['Chart', 'Table'],
}: {
  value: View
  onChange: (next: View) => void
  labels?: [string, string]
}) {
  return (
    <div className="segmented small" role="group" aria-label="Show as">
      {(['chart', 'table'] as const).map((v, i) => (
        <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>
          {labels[i]}
        </button>
      ))}
    </div>
  )
}
