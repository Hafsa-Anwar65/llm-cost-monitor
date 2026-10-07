import { useMemo, useState, type ReactNode } from 'react'

export interface Column<T> {
  key: string
  header: string
  numeric?: boolean
  wrap?: boolean
  /** The value used for sorting. */
  value: (row: T) => string | number | null
  /** How the cell looks; falls back to `value`. */
  render?: (row: T) => ReactNode
}

interface Sort {
  key: string
  dir: 'asc' | 'desc'
}

export function DataTable<T>({
  rows,
  columns,
  caption,
  defaultSort,
}: {
  rows: T[]
  columns: Column<T>[]
  caption: string
  defaultSort?: Sort
}) {
  const [sort, setSort] = useState<Sort | null>(defaultSort ?? null)

  const sorted = useMemo(() => {
    const col = sort && columns.find((c) => c.key === sort.key)
    if (!sort || !col) return rows
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = col.value(a)
      const bv = col.value(b)
      if (av === bv) return 0
      if (av === null) return 1
      if (bv === null) return -1
      return (av < bv ? -1 : 1) * dir
    })
  }, [rows, columns, sort])

  const toggle = (col: Column<T>) =>
    setSort((s) =>
      s?.key === col.key
        ? { key: col.key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
        : { key: col.key, dir: col.numeric ? 'desc' : 'asc' },
    )

  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={col.numeric ? 'num' : undefined}
                aria-sort={sort?.key === col.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                <button type="button" onClick={() => toggle(col)}>
                  {col.header}
                  {sort?.key === col.key && <span aria-hidden="true">{sort.dir === 'asc' ? '↑' : '↓'}</span>}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col.key} className={[col.numeric ? 'num' : '', col.wrap ? 'wrap' : ''].join(' ').trim() || undefined}>
                  {col.render ? col.render(row) : (col.value(row) ?? '–')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
