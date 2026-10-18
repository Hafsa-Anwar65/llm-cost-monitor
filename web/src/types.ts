export type RangeKey = '24h' | '7d' | '30d' | 'all'
export type Unit = 'hour' | 'day' | 'week'

export interface Summary {
  cost: number
  prev_cost: number | null
  requests: number
  input_tokens: number
  output_tokens: number
  cache_tokens: number
  p50: number | null
  p95: number | null
  p99: number | null
  ttft_p50: number | null
  error_rate: number
}

/** `slot` is the model's fixed colour slot (0-7); null means the folded "Other" series. */
export interface SeriesDef {
  key: string
  slot: number | null
}

export interface SpendPoint {
  t: string
  values: Record<string, number>
}

export interface LatencyPoint {
  t: string
  n: number
  p50: number | null
  p95: number | null
  p99: number | null
}

export interface ModelRow {
  model: string
  requests: number
  cost: number
  p50: number | null
  p95: number | null
  p99: number | null
  ttft_p50: number | null
  error_rate: number
}

export interface Share {
  name: string
  cost: number
  requests: number
}

export interface RequestRow {
  id: number
  ts: string
  provider: string
  model: string
  user: string | null
  feature: string | null
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cost: number
  latency_ms: number | null
  status: number
  error: string | null
}

export type CheckStatus = 'ok' | 'warn' | 'fail' | 'na'

export interface AccuracyCheck {
  id: string
  label: string
  status: CheckStatus
  value: string
  detail: string
}

export interface Accuracy {
  score: number
  grade: 'High' | 'Medium' | 'Low'
  checks: AccuracyCheck[]
  requests_checked: number
}

export interface Dashboard {
  range: RangeKey
  tz: string
  bucket: Unit
  generated_at: string
  last_request_at: string | null
  summary: Summary
  spend: { series: SeriesDef[]; points: SpendPoint[] }
  latency: LatencyPoint[]
  by_model: ModelRow[]
  /** Requests by weekday (Mon first) and three-hour block of the day. */
  activity: number[][]
  by_user: Share[]
  by_feature: Share[]
  top_requests: RequestRow[]
  failures: RequestRow[]
  unpriced: { count: number; models: string[] }
  budget: { limit: number | null; today: number }
  meta: { models: string[]; providers: string[]; users: string[]; features: string[] }
  accuracy: Accuracy
}

export interface Query {
  range: RangeKey
  providers: string[]
  models: string[]
  users: string[]
  features: string[]
}
