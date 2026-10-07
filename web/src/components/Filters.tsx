import { useEffect, useId, useRef, useState } from 'react'
import type { RangeKey } from '../types'
import { Chevron } from './icons'

const RANGES: { key: RangeKey; label: string }[] = [
  { key: '24h', label: '24h' },
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: 'all', label: 'All time' },
]

export function RangeControl({ value, onChange }: { value: RangeKey; onChange: (next: RangeKey) => void }) {
  return (
    <div className="segmented" role="group" aria-label="Time range">
      {RANGES.map((r) => (
        <button key={r.key} type="button" aria-pressed={value === r.key} onClick={() => onChange(r.key)}>
          {r.label}
        </button>
      ))}
    </div>
  )
}

interface MultiSelectProps {
  label: string
  options: string[]
  value: string[]
  onChange: (next: string[]) => void
}

export function MultiSelect({ label, options, value, onChange }: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onPointer = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const summary =
    value.length === 0 ? `All ${label}` : value.length === 1 ? value[0] : `${value.length} ${label}`
  const toggle = (option: string) =>
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option])

  return (
    <div className="picker" ref={root}>
      <button
        type="button"
        className="picker-button"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        data-active={value.length > 0}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{summary}</span>
        <Chevron />
      </button>
      {open && (
        <div className="picker-panel" id={panelId} role="group" aria-label={`Filter by ${label}`}>
          {options.map((option) => (
            <label key={option} className="picker-option">
              <input type="checkbox" checked={value.includes(option)} onChange={() => toggle(option)} />
              <span>{option}</span>
            </label>
          ))}
          {value.length > 0 && (
            <button type="button" className="picker-clear" onClick={() => onChange([])}>
              Clear selection
            </button>
          )}
        </div>
      )}
    </div>
  )
}
