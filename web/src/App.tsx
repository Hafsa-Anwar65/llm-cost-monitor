import { useState } from 'react'
import { toSearch, useActiveSection, useDashboard, useTheme } from './hooks'
import { stamp } from './format'
import type { Dashboard, RangeKey } from './types'
import { MultiSelect, RangeControl } from './components/Filters'
import { AccuracyCard } from './components/AccuracyCard'
import { ActivityCard } from './components/Activity'
import { Hero } from './components/Hero'
import { KeyFigures } from './components/KeyFigures'
import { LatencySection, ModelsCard } from './components/LatencySection'
import { RankedList } from './components/RankedList'
import { CostliestCard, FailuresCard } from './components/RequestTables'
import { SpendSection } from './components/SpendChart'
import { IconDownload, IconTag, IconUsers, Logo, Moon, Sun, Warning } from './components/icons'

const NAV = [
  { id: 'overview', label: 'Overview' },
  { id: 'spend', label: 'Spend' },
  { id: 'latency', label: 'Latency' },
  { id: 'requests', label: 'Requests' },
  { id: 'accuracy', label: 'Accuracy' },
]

export default function App() {
  const [range, setRange] = useState<RangeKey>('7d')
  const [providers, setProviders] = useState<string[]>([])
  const [models, setModels] = useState<string[]>([])
  const [users, setUsers] = useState<string[]>([])
  const [features, setFeatures] = useState<string[]>([])
  const [live, setLive] = useState(false)
  const { theme, toggle } = useTheme()
  const query = { range, providers, models, users, features }
  const { data, error, loading, reload } = useDashboard(query, live)
  const reportUrl = (format: 'md' | 'csv') => `/api/report?format=${format}&${toSearch(query)}`
  const active = useActiveSection(NAV.map((n) => n.id), data !== null)

  const filtersActive = providers.length + models.length + users.length + features.length > 0
  const clearFilters = () => {
    setProviders([])
    setModels([])
    setUsers([])
    setFeatures([])
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <Logo />
            <span>
              LLM Cost <span className="brand-soft">Monitor</span>
            </span>
          </div>
          {data && data.meta.models.length > 0 && data.summary.requests > 0 && (
            <nav className="nav" aria-label="Sections">
              {NAV.map((n) => (
                <a key={n.id} href={`#${n.id}`} aria-current={active === n.id ? 'true' : undefined}>
                  {n.label}
                </a>
              ))}
            </nav>
          )}
          <div className="toggles">
            <button type="button" className="pill" aria-pressed={live} onClick={() => setLive((l) => !l)} title="Refresh every 5 seconds">
              <span className="dot" />
              Live
            </button>
            <button
              type="button"
              className="icon-button"
              onClick={toggle}
              aria-label={theme === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
            </button>
          </div>
        </div>
      </header>

      <main className="page" data-refreshing={loading && data !== null}>
        {!data && !error && (
          <p className="state" role="status">
            Loading the dashboard…
          </p>
        )}

        {!data && error && (
          <div className="state">
            <h1>Can&apos;t load the dashboard</h1>
            <p>{error} Check that the proxy is running, then try again.</p>
            <pre>uvicorn proxy.main:app --port 8000</pre>
            <button type="button" onClick={reload}>
              Try again
            </button>
          </div>
        )}

        {data && data.meta.models.length === 0 && <EmptyState />}

        {data && data.meta.models.length > 0 && (
          <>
            <div className="greet" id="overview">
              <h1>
                Where your <span>LLM budget went</span>
              </h1>
              <RangeControl value={range} onChange={setRange} />
            </div>
            <div className="filters" role="group" aria-label="Filters">
              {data.meta.providers.length > 1 && (
                <MultiSelect label="providers" options={data.meta.providers} value={providers} onChange={setProviders} />
              )}
              <MultiSelect label="models" options={data.meta.models} value={models} onChange={setModels} />
              {data.meta.users.length > 0 && (
                <MultiSelect label="users" options={data.meta.users} value={users} onChange={setUsers} />
              )}
              {data.meta.features.length > 0 && (
                <MultiSelect label="features" options={data.meta.features} value={features} onChange={setFeatures} />
              )}
              {filtersActive && (
                <button type="button" className="link-button" onClick={clearFilters}>
                  Clear filters
                </button>
              )}
              {data.summary.requests > 0 && (
                <div className="downloads" role="group" aria-label="Download this view">
                  <a className="pill" href={reportUrl('md')} download title="Summary, accuracy checks and breakdowns as a Markdown report">
                    <IconDownload />
                    Report
                  </a>
                  <a className="pill" href={reportUrl('csv')} download title="Every request in this view as a CSV file">
                    <IconDownload />
                    CSV
                  </a>
                </div>
              )}
            </div>
            {error && (
              <div className="banner" data-tone="error" role="alert">
                <Warning color="var(--crit)" />
                <span>Showing the last data we have. {error}</span>
                <button type="button" onClick={reload}>
                  Retry
                </button>
              </div>
            )}
            {data.unpriced.count > 0 && (
              <div className="banner" role="status">
                <Warning />
                <span>
                  {data.unpriced.count.toLocaleString('en-US')} requests used models with no price (
                  {data.unpriced.models.join(', ')}). Their cost counts as $0 until you add them to <code>pricing.json</code>.
                </span>
              </div>
            )}
            {data.summary.requests === 0 ? (
              <div className="state">
                <h1>No requests match these filters</h1>
                <p>Try a longer time range, or clear the filters.</p>
                {filtersActive && (
                  <button type="button" onClick={clearFilters}>
                    Clear filters
                  </button>
                )}
              </div>
            ) : (
              <Body data={data} />
            )}
            <p className="footnote">
              Times are in {data.tz}.
              {data.last_request_at && ` Last request ${stamp(data.last_request_at)}.`}
            </p>
          </>
        )}
      </main>
    </>
  )
}

function Body({ data }: { data: Dashboard }) {
  return (
    <>
      <Hero data={data} />
      <KeyFigures summary={data.summary} />
      <div className="grid">
        <SpendSection series={data.spend.series} points={data.spend.points} unit={data.bucket} />
        <ActivityCard grid={data.activity} />
        <LatencySection points={data.latency} unit={data.bucket} />
        <CostliestCard rows={data.top_requests} />
        <ModelsCard models={data.by_model} />
        <RankedList
          id="users"
          icon={<IconUsers />}
          title="By user"
          items={data.by_user}
          color="var(--accent)"
          hint="Add an X-User-Tag header to your requests to see spend per user."
        />
        <RankedList
          id="features"
          icon={<IconTag />}
          title="By feature"
          items={data.by_feature}
          color="var(--lime)"
          hint="Add an X-Feature-Tag header to your requests to see spend per feature."
        />
        <FailuresCard rows={data.failures} />
        <AccuracyCard accuracy={data.accuracy} />
      </div>
    </>
  )
}

function EmptyState() {
  return (
    <div className="state">
      <h1>No requests yet</h1>
      <p>Point your SDK at the proxy and the first request will show up here within seconds.</p>
      <pre>{`Anthropic   base_url="http://localhost:8000/anthropic"
OpenAI      base_url="http://localhost:8000/openai/v1"`}</pre>
      <p>Just want to look around? Load sample data, then reload this page.</p>
      <pre>python scripts/seed_demo_data.py</pre>
    </div>
  )
}
