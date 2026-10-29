'use client'

import { memo, useDeferredValue, useMemo, useState } from 'react'
import { useStoredState } from '@/hooks/use-stored-state'
import type { Envelope } from '@/lib/contracts'
import { eventTone, formatT, GROUPS, groupOf, payloadSummary, toneClasses, type Group } from '@/lib/format'
import { countBy, filterEvents, topicOf } from '@/lib/timeline-filter'
import { cn } from '@/lib/utils'

const MAX_ROWS = 250

type Saved = { hiddenGroups: Group[]; hiddenTypes: string[]; hiddenTopics: string[]; showTopic: boolean }
const DEFAULTS: Saved = { hiddenGroups: ['gps', 'radar'], hiddenTypes: [], hiddenTopics: [], showTopic: false }

/** Lo guardado puede venir incompleto o de una versión anterior: se completa con los valores por defecto. */
function revive(raw: unknown): Saved {
  const r = (raw ?? {}) as Partial<Saved>
  const list = (v: unknown, d: string[]) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : d)
  return {
    hiddenGroups: list(r.hiddenGroups, DEFAULTS.hiddenGroups) as Group[],
    hiddenTypes: list(r.hiddenTypes, []),
    hiddenTopics: list(r.hiddenTopics, []),
    showTopic: typeof r.showTopic === 'boolean' ? r.showTopic : false,
  }
}

const toggled = (list: string[], key: string) => (list.includes(key) ? list.filter((k) => k !== key) : [...list, key])

export const EventTimeline = memo(function EventTimeline({ events, cursor, total }: { events: Envelope[]; cursor: number; total: number }) {
  const [saved, setSaved] = useStoredState<Saved>('poc-timeline-v1', DEFAULTS, revive)
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)

  const filter = useMemo(
    () => ({ hiddenGroups: new Set(saved.hiddenGroups), hiddenTypes: new Set(saved.hiddenTypes), hiddenTopics: new Set(saved.hiddenTopics), query: deferredQuery }),
    [saved, deferredQuery],
  )
  const visible = useMemo(() => filterEvents(events, filter), [events, filter])
  const rows = useMemo(() => visible.slice(-MAX_ROWS).reverse(), [visible])
  const types = useMemo(() => countBy(events, (e) => e.type), [events])
  const topics = useMemo(() => countBy(events, topicOf), [events])

  const set = (patch: Partial<Saved>) => setSaved((prev) => ({ ...prev, ...patch }))
  const columns = saved.showTopic ? 'grid-cols-[4.5rem_14rem_1fr]' : 'grid-cols-[4.5rem_11rem_1fr]'

  return (
    <section aria-labelledby="timeline-title" className="flex min-h-0 flex-1 flex-col bg-card">
      <header className="flex flex-col gap-1.5 border-b border-border px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <h2 id="timeline-title" className="text-sm font-semibold text-foreground">
            Event timeline
          </h2>
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            {events.length} events · simulation {cursor}/{total}
          </span>
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-label="Filter by source">
          {GROUPS.map((g) => (
            <li key={g.id}>
              <label className="flex cursor-pointer items-center gap-1">
                <input
                  type="checkbox"
                  checked={!saved.hiddenGroups.includes(g.id)}
                  onChange={() => set({ hiddenGroups: toggled(saved.hiddenGroups, g.id) as Group[] })}
                  className="size-3 accent-primary"
                />
                {g.label}
              </label>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search type, id, topic or content…"
            aria-label="Search events"
            className="h-7 min-w-48 flex-1 rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-ring"
          />
          <FilterMenu label="Type" items={types} hidden={saved.hiddenTypes} onToggle={(k) => set({ hiddenTypes: toggled(saved.hiddenTypes, k) })} onAll={() => set({ hiddenTypes: [] })} />
          <FilterMenu label="Topic" items={topics} hidden={saved.hiddenTopics} onToggle={(k) => set({ hiddenTopics: toggled(saved.hiddenTopics, k) })} onAll={() => set({ hiddenTopics: [] })} />
          <label className="flex cursor-pointer items-center gap-1.5 text-muted-foreground">
            <input type="checkbox" role="switch" checked={saved.showTopic} onChange={(e) => set({ showTopic: e.target.checked })} className="size-3 accent-primary" />
            Show topic and source
          </label>
          {visible.length !== events.length && (
            <span className="font-mono text-[11px] text-muted-foreground" data-testid="timeline-shown">
              {visible.length} shown
            </span>
          )}
        </div>
      </header>

      <ol className="min-h-48 flex-1 overflow-y-auto font-mono text-xs" aria-live="off">
        {rows.length === 0 && (
          <li className="px-4 py-6 text-center font-sans text-sm text-muted-foreground">
            {events.length === 0 ? 'No events yet.' : 'No events match the filters.'}
          </li>
        )}
        {rows.map((event, i) => (
          <li key={event.event_id} className={cn('grid items-center gap-3 border-b border-border/60 px-4 py-1.5', columns, i === 0 && 'bg-primary/5')}>
            <span className="tabular-nums text-muted-foreground">{formatT(event.sim_time)}</span>
            <span className="flex min-w-0 flex-col">
              <span className={cn('truncate self-start rounded-sm px-1.5 py-0.5 text-[11px] font-medium', toneClasses[eventTone(event)])}>{event.type}</span>
              {saved.showTopic && (
                <span className="truncate text-[10px] text-muted-foreground" title={event.topic} data-testid="event-topic">
                  {topicOf(event)} · {event.source}
                </span>
              )}
            </span>
            <span className="truncate text-foreground/80" title={payloadSummary(event)}>
              {payloadSummary(event)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
})

function FilterMenu({ label, items, hidden, onToggle, onAll }: { label: string; items: [string, number][]; hidden: string[]; onToggle: (key: string) => void; onAll: () => void }) {
  return (
    <details className="relative">
      <summary className="flex h-7 cursor-pointer list-none items-center gap-1 rounded-md border border-border bg-background px-2 text-xs text-foreground hover:bg-muted [&::-webkit-details-marker]:hidden">
        {label}
        {hidden.length > 0 && <span className="font-mono text-[10px] text-accent">−{hidden.length}</span>}
        <span aria-hidden="true">▾</span>
      </summary>
      <div className="absolute left-0 z-30 mt-1 flex max-h-64 w-64 flex-col gap-0.5 overflow-auto rounded-md border border-border bg-card p-2 shadow-md" role="group" aria-label={`Filter by ${label.toLowerCase()}`}>
        <button type="button" onClick={onAll} disabled={hidden.length === 0} className="mb-1 self-start text-[11px] font-medium text-primary disabled:text-muted-foreground">
          Show all
        </button>
        {items.length === 0 && <span className="text-[11px] text-muted-foreground">Nothing yet.</span>}
        {items.map(([key, n]) => (
          <label key={key} className="flex cursor-pointer items-center gap-1.5 text-[11px] text-foreground">
            <input type="checkbox" checked={!hidden.includes(key)} onChange={() => onToggle(key)} className="size-3 accent-primary" />
            <span className="min-w-0 flex-1 truncate font-mono">{key}</span>
            <span className="font-mono text-muted-foreground">{n}</span>
          </label>
        ))}
      </div>
    </details>
  )
}
