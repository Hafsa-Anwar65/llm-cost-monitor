import { useState } from 'react'
import { duration, int, money, stamp } from '../format'
import type { RequestRow } from '../types'
import { DataTable, type Column } from './DataTable'
import { CheckCircle, IconAlert, IconList, Stop } from './icons'
import { Section, ViewToggle, type View } from './Section'

const STATUS_LABEL: Record<number, string> = {
  400: 'Bad request',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not found',
  408: 'Timed out',
  413: 'Too large',
  429: 'Rate limited',
  500: 'Server error',
  502: 'Upstream unreachable',
  503: 'Unavailable',
  529: 'Overloaded',
}

const dash = (v: string | null) => v ?? '–'

export function CostliestTable({ rows }: { rows: RequestRow[] }) {
  const columns: Column<RequestRow>[] = [
    { key: 'ts', header: 'Time', value: (r) => r.ts, render: (r) => stamp(r.ts) },
    { key: 'model', header: 'Model', value: (r) => r.model },
    { key: 'user', header: 'User', value: (r) => r.user, render: (r) => dash(r.user) },
    { key: 'feature', header: 'Feature', value: (r) => r.feature, render: (r) => dash(r.feature) },
    { key: 'in', header: 'Input tokens', numeric: true, value: (r) => r.input_tokens + r.cache_read_tokens, render: (r) => int(r.input_tokens + r.cache_read_tokens) },
    { key: 'out', header: 'Output tokens', numeric: true, value: (r) => r.output_tokens, render: (r) => int(r.output_tokens) },
    { key: 'lat', header: 'Latency', numeric: true, value: (r) => r.latency_ms, render: (r) => duration(r.latency_ms) },
    { key: 'cost', header: 'Cost', numeric: true, value: (r) => r.cost, render: (r) => money(r.cost) },
  ]
  return <DataTable rows={rows} columns={columns} caption="The most expensive requests in this range" defaultSort={{ key: 'cost', dir: 'desc' }} />
}

export function FailuresTable({ rows }: { rows: RequestRow[] }) {
  const columns: Column<RequestRow>[] = [
    { key: 'ts', header: 'Time', value: (r) => r.ts, render: (r) => stamp(r.ts) },
    { key: 'model', header: 'Model', value: (r) => r.model },
    {
      key: 'status',
      header: 'Status',
      value: (r) => r.status,
      render: (r) => (
        <span className="chip">
          <Stop />
          {r.status} {STATUS_LABEL[r.status] ?? 'Error'}
        </span>
      ),
    },
    { key: 'user', header: 'User', value: (r) => r.user, render: (r) => dash(r.user) },
    { key: 'error', header: 'Message', wrap: true, value: (r) => r.error, render: (r) => dash(r.error) },
  ]
  return <DataTable rows={rows} columns={columns} caption="The most recent failed requests" />
}

const tag = (v: string | null) => v ?? 'untagged'

export function CostliestCard({ rows }: { rows: RequestRow[] }) {
  const [view, setView] = useState<View>('chart')
  return (
    <Section
      id="requests"
      icon={<IconList />}
      title="Costliest requests"
      note="The most expensive calls in this range"
      actions={<ViewToggle value={view} onChange={setView} labels={['List', 'Table']} />}
    >
      {view === 'table' ? (
        <div className="table-wrap">
          <CostliestTable rows={rows} />
        </div>
      ) : (
        <ol className="rows">
          {rows.slice(0, 7).map((r) => (
            <li key={r.id} title={`${stamp(r.ts)} - ${int(r.input_tokens + r.cache_read_tokens)} in, ${int(r.output_tokens)} out, ${duration(r.latency_ms)}`}>
              <span className="row-main">
                <strong>{r.model}</strong>
                <small>
                  {stamp(r.ts)} · {duration(r.latency_ms)}
                </small>
              </span>
              <span className="tag" data-empty={r.feature === null}>
                <i />
                {tag(r.feature)}
              </span>
              <span className="row-amount">{money(r.cost)}</span>
            </li>
          ))}
        </ol>
      )}
    </Section>
  )
}

export function FailuresCard({ rows }: { rows: RequestRow[] }) {
  const [view, setView] = useState<View>('chart')
  return (
    <Section
      id="failures"
      icon={<IconAlert />}
      title="Recent failures"
      note="Requests that came back with an error"
      actions={rows.length > 0 ? <ViewToggle value={view} onChange={setView} labels={['List', 'Table']} /> : undefined}
    >
      {rows.length === 0 ? (
        <p className="all-good">
          <CheckCircle />
          No failed requests in this range.
        </p>
      ) : view === 'table' ? (
        <div className="table-wrap">
          <FailuresTable rows={rows} />
        </div>
      ) : (
        <ol className="rows">
          {rows.slice(0, 7).map((r) => (
            <li key={r.id} title={r.error ?? undefined}>
              <span className="row-main">
                <strong>{r.model}</strong>
                <small>{stamp(r.ts)}</small>
              </span>
              <span className="tag" data-tone="bad">
                <i />
                {r.status} {STATUS_LABEL[r.status] ?? 'Error'}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Section>
  )
}
