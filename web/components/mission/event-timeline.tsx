'use client'

import { memo, useMemo, useState } from 'react'
import type { Envelope } from '@/lib/contracts'
import { eventTone, formatT, GROUPS, groupOf, payloadSummary, toneClasses, type Group } from '@/lib/format'
import { cn } from '@/lib/utils'

const MAX_ROWS = 250
const HIDDEN_BY_DEFAULT: Group[] = ['gps', 'radar']

export const EventTimeline = memo(function EventTimeline({ events, cursor, total }: { events: Envelope[]; cursor: number; total: number }) {
  const [hidden, setHidden] = useState<Set<Group>>(new Set(HIDDEN_BY_DEFAULT))

  const rows = useMemo(() => {
    const visible = events.filter((e) => !hidden.has(groupOf(e)))
    return visible.slice(-MAX_ROWS).reverse()
  }, [events, hidden])

  const toggle = (g: Group) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })

  return (
    <section aria-labelledby="timeline-title" className="flex min-h-0 flex-1 flex-col bg-card">
      <header className="flex flex-col gap-1.5 border-b border-border px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <h2 id="timeline-title" className="text-sm font-semibold text-foreground">
            Event timeline
          </h2>
          <span className="font-mono text-xs tabular-nums text-muted-foreground" title="Events shown; and simulation events published out of those expected without interventions">
            {events.length} events · simulation {cursor}/{total}
          </span>
          <span className="ml-auto text-[11px] italic text-muted-foreground">"Simulator": the agent does not see those events</span>
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-label="Filter by source">
          {GROUPS.map((g) => (
            <li key={g.id}>
              <label className="flex cursor-pointer items-center gap-1">
                <input type="checkbox" checked={!hidden.has(g.id)} onChange={() => toggle(g.id)} className="size-3 accent-primary" />
                {g.label}
              </label>
            </li>
          ))}
        </ul>
      </header>

      <ol className="min-h-48 flex-1 overflow-y-auto font-mono text-xs" aria-live="off">
        {rows.length === 0 && (
          <li className="px-4 py-6 text-center font-sans text-sm text-muted-foreground">No events yet. Load a scenario and press Start.</li>
        )}
        {rows.map((event, i) => (
          <li
            key={event.event_id}
            className={cn('grid grid-cols-[4.5rem_11rem_1fr] items-center gap-3 border-b border-border/60 px-4 py-1.5', i === 0 && 'bg-primary/5')}
          >
            <span className="tabular-nums text-muted-foreground">{formatT(event.sim_time)}</span>
            <span className={cn('truncate rounded-sm px-1.5 py-0.5 text-[11px] font-medium', toneClasses[eventTone(event)])}>{event.type}</span>
            <span className="truncate text-foreground/80" title={payloadSummary(event)}>
              {payloadSummary(event)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
})
