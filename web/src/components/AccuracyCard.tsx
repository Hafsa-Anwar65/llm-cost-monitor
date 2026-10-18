import type { Accuracy, CheckStatus } from '../types'
import { CheckCircle, IconShield, Stop, Warning } from './icons'
import { Section } from './Section'

const LABEL: Record<CheckStatus, string> = { ok: 'Pass', warn: 'Check', fail: 'Fail', na: 'n/a' }

function StatusIcon({ status }: { status: CheckStatus }) {
  if (status === 'ok') return <CheckCircle />
  if (status === 'warn') return <Warning />
  if (status === 'fail') return <Stop />
  return <span className="acc-na" aria-hidden="true">–</span>
}

/** A ring that fills to the score. Colour follows the grade, the number carries the meaning. */
function ScoreRing({ score, grade }: { score: number; grade: Accuracy['grade'] }) {
  const r = 44
  const c = 2 * Math.PI * r
  const tone = grade === 'High' ? 'var(--good)' : grade === 'Medium' ? 'var(--warn)' : 'var(--crit)'
  return (
    <div className="acc-score">
      <svg viewBox="0 0 104 104" width="132" height="132" role="img" aria-label={`Accuracy score ${score} out of 100`}>
        <circle cx="52" cy="52" r={r} fill="none" stroke="var(--sunken)" strokeWidth="9" />
        <circle
          cx="52"
          cy="52"
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`}
          transform="rotate(-90 52 52)"
        />
        <text x="52" y="56" textAnchor="middle" className="acc-score-num">
          {score}
        </text>
        <text x="52" y="72" textAnchor="middle" className="acc-score-of">
          / 100
        </text>
      </svg>
      <p className="acc-grade" style={{ color: tone }}>
        {grade} confidence
      </p>
    </div>
  )
}

export function AccuracyCard({ accuracy }: { accuracy: Accuracy }) {
  const issues = accuracy.checks.filter((c) => c.status === 'warn' || c.status === 'fail').length
  return (
    <Section
      id="accuracy"
      className="span-3"
      icon={<IconShield />}
      title="Data accuracy"
      note={
        issues === 0
          ? `All checks passed on ${accuracy.requests_checked.toLocaleString('en-US')} requests. You can trust these numbers.`
          : `${issues} ${issues === 1 ? 'check needs' : 'checks need'} attention before you rely on these numbers.`
      }
    >
      <div className="acc">
        <ScoreRing score={accuracy.score} grade={accuracy.grade} />
        <ul className="acc-list">
          {accuracy.checks.map((c) => (
            <li key={c.id} data-status={c.status}>
              <span className="acc-icon">
                <StatusIcon status={c.status} />
              </span>
              <div className="acc-text">
                <p className="acc-label">
                  {c.label}
                  <span className="acc-badge" data-status={c.status}>
                    {LABEL[c.status]}
                  </span>
                </p>
                <p className="acc-detail">{c.detail}</p>
              </div>
              <span className="acc-value">{c.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  )
}
