/** Each model keeps one of eight fixed hues; the folded "Other" series is neutral gray. */
export const seriesColor = (slot: number | null): string =>
  slot === null ? 'var(--other)' : `var(--s${slot + 1})`
