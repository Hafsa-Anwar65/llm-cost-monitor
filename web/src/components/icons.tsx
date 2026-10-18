import type { SVGProps } from 'react'

const base: SVGProps<SVGSVGElement> = {
  width: 16,
  height: 16,
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

export const Logo = () => (
  <svg className="logo" width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
    <defs>
      <linearGradient id="logo-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#8b5cff" />
        <stop offset="1" stopColor="#4b1fd1" />
      </linearGradient>
      <linearGradient id="logo-arc" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#3ac7ff" />
        <stop offset="1" stopColor="#c6f432" />
      </linearGradient>
    </defs>
    <rect width="32" height="32" rx="9" fill="url(#logo-bg)" />
    <path d="M7.5 21.5a8.5 8.5 0 0 1 17 0" fill="none" stroke="#fff" strokeOpacity=".22" strokeWidth="3" strokeLinecap="round" />
    <path d="M7.5 21.5a8.5 8.5 0 0 1 14.51-6.01" fill="none" stroke="url(#logo-arc)" strokeWidth="3" strokeLinecap="round" />
    <path d="M16 21.5l4-4" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
    <circle cx="16" cy="21.5" r="2" fill="#fff" />
  </svg>
)

export const IconShield = () => (
  <svg {...base}>
    <path d="M8 1.8l5.2 2v4c0 3.2-2.2 5.4-5.2 6.4-3-1-5.2-3.2-5.2-6.4v-4L8 1.8z" />
    <path d="M5.6 8.1l1.7 1.7 3.2-3.4" />
  </svg>
)

export const IconDownload = () => (
  <svg {...base}>
    <path d="M8 2.5v7.5M4.8 7l3.2 3.2L11.2 7M2.5 12.5v1h11v-1" />
  </svg>
)

export const Chevron = () => (
  <svg {...base} width={12} height={12}>
    <path d="M3 6l5 5 5-5" />
  </svg>
)

export const Sun = () => (
  <svg {...base}>
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" />
  </svg>
)

export const Moon = () => (
  <svg {...base}>
    <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z" />
  </svg>
)

export const CheckCircle = ({ color = 'var(--good)' }: { color?: string }) => (
  <svg {...base} style={{ color }}>
    <circle cx="8" cy="8" r="6.2" />
    <path d="M5.3 8.2l1.8 1.8 3.6-3.9" />
  </svg>
)

export const Warning = ({ color = 'var(--warn)' }: { color?: string }) => (
  <svg {...base} style={{ color }}>
    <path d="M8 2.2l6.2 11H1.8L8 2.2z" />
    <path d="M8 6.8v3M8 11.8v.1" />
  </svg>
)

export const Stop = ({ color = 'var(--crit)' }: { color?: string }) => (
  <svg {...base} style={{ color }}>
    <circle cx="8" cy="8" r="6.2" />
    <path d="M5.7 5.7l4.6 4.6M10.3 5.7l-4.6 4.6" />
  </svg>
)

export const IconSpend = () => (
  <svg {...base}>
    <path d="M2.5 13.5V2.5M2.5 13.5h11" />
    <path d="M5.5 10.5v-2M8.5 10.5v-5M11.5 10.5v-3" />
  </svg>
)

export const IconLatency = () => (
  <svg {...base}>
    <circle cx="8" cy="8.5" r="5.7" />
    <path d="M8 5.2V8.7l2.2 1.3M6.3 1.5h3.4" />
  </svg>
)

export const IconActivity = () => (
  <svg {...base}>
    <rect x="2" y="2" width="5" height="5" rx="1.2" />
    <rect x="9" y="2" width="5" height="5" rx="1.2" />
    <rect x="2" y="9" width="5" height="5" rx="1.2" />
    <rect x="9" y="9" width="5" height="5" rx="1.2" />
  </svg>
)

export const IconList = () => (
  <svg {...base}>
    <path d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.1M2.5 8h.1M2.5 12h.1" />
  </svg>
)

export const IconUsers = () => (
  <svg {...base}>
    <circle cx="6" cy="5.5" r="2.4" />
    <path d="M1.8 13c.3-2.4 2-3.7 4.2-3.7s3.9 1.3 4.2 3.7M10.5 3.3a2.3 2.3 0 0 1 0 4.4M12.2 9.6c1.2.5 2 1.6 2.2 3.4" />
  </svg>
)

export const IconTag = () => (
  <svg {...base}>
    <path d="M2 2.5h5.5l6.5 6.5-5 5L2.5 7.5 2 2.5z" />
    <circle cx="5.2" cy="5.2" r=".7" />
  </svg>
)

export const IconAlert = () => (
  <svg {...base}>
    <circle cx="8" cy="8" r="6.2" />
    <path d="M8 4.7v3.8M8 11v.1" />
  </svg>
)

export const ArrowUp = () => (
  <svg {...base} width={11} height={11} strokeWidth={2}>
    <path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" />
  </svg>
)

export const ArrowDown = () => (
  <svg {...base} width={11} height={11} strokeWidth={2}>
    <path d="M8 3v10M3.5 8.5L8 13l4.5-4.5" />
  </svg>
)
