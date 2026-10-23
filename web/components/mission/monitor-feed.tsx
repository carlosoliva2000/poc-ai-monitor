'use client'

import { ArrowRight, Repeat2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type {
  AgentActivity,
  AlertClosed,
  Anomaly,
  Detection,
  DetectionAcknowledged,
  DetectionCleared,
  Envelope,
} from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import { stripFieldValues } from '@/lib/clean-text'
import { CAUSE_LABEL, CHECK_LABEL, formatT, SEVERITY_LABEL, SOURCE_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import { TypingDots } from './chat-panel'

const SEVERITY_CLASS = {
  low: 'bg-primary/10 text-primary',
  medium: 'bg-warning/20 text-foreground',
  high: 'bg-destructive text-destructive-foreground',
} as const

type Props = {
  events: Envelope[]
  data: Derived
  activity: Record<string, AgentActivity>
}

/** Quién habla: el detector (reglas), el monitor (LLM) o el módulo (cierre sin LLM). */
const Who = ({ label, className, t }: { label: string; className: string; t: number }) => (
  <div className="flex items-center justify-between gap-2 font-mono text-[11px]">
    <span className={cn('font-medium', className)}>{label}</span>
    <span className="tabular-nums text-muted-foreground">{formatT(t)}</span>
  </div>
)

export function MonitorFeed({ events, data, activity }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const feed = events.filter((e) => e.source === 'ai-detector' || e.source === 'ai-monitor')
  const pendingIds = new Set(data.pending.map((e) => e.event_id))
  const byId = new Map(feed.map((e) => [e.event_id, e]))
  const busy = Boolean(activity.monitor)

  useEffect(() => {
    const el = scrollRef.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [feed.length, data.pending.length])

  return (
    <div className="flex min-h-0 flex-[3] flex-col">
      <Episodes data={data} />
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}
        className="flex min-h-24 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3"
        role="log"
        aria-live="polite"
        data-testid="monitor-feed"
      >
        {feed.length === 0 && (
          <p className="m-auto max-w-64 text-center text-sm leading-relaxed text-muted-foreground text-pretty">
            Waiting for the detector. When a rule fires, the monitor will diagnose the cause and publish an alert here.
          </p>
        )}
        {feed.map((e) => (
          <div key={e.event_id} className="flex flex-col gap-2">
            <FeedEntry event={e} data={data} byId={byId} />
            {pendingIds.has(e.event_id) && <Analyzing event={e} busy={busy} />}
          </div>
        ))}
      </div>
    </div>
  )
}

function Episodes({ data }: { data: Derived }) {
  if (data.episodes.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1.5 border-b border-border px-4 py-2 text-xs" aria-label="Alerts (one per episode)">
      {data.episodes.map((ep) => {
        const a = ep.head.event.payload
        return (
          <li
            key={ep.label}
            className={cn('flex items-center gap-1.5 rounded-full border px-2 py-0.5', ep.open ? 'border-destructive/50 bg-destructive/5' : 'border-border text-muted-foreground')}
            title={`${a.alert_id} · ${a.summary}`}
          >
            <span className="font-mono font-medium">{ep.label}</span>
            <span>{CAUSE_LABEL[a.cause]}</span>
            <span className={cn('rounded-sm px-1 text-[10px] font-medium', SEVERITY_CLASS[a.severity])}>{SEVERITY_LABEL[a.severity]}</span>
            <span>{ep.open ? 'open' : 'closed'}</span>
            {ep.chain.length > 1 && <span className="text-muted-foreground">· {ep.chain.length} alerts</span>}
          </li>
        )
      })}
    </ul>
  )
}

function Analyzing({ event, busy }: { event: Envelope; busy: boolean }) {
  const p = event.payload as unknown as { detection_id: string }
  const what = event.type === 'DetectionCleared' ? `the closure of ${p.detection_id}` : p.detection_id
  return (
    <div className="flex items-center gap-2 pl-3 text-xs text-muted-foreground">
      <span className="font-mono font-medium text-primary">MONITOR</span>
      analysing {what}…
      {busy ? <TypingDots /> : <span>(queued)</span>}
    </div>
  )
}

function FeedEntry({ event, data, byId }: { event: Envelope; data: Derived; byId: Map<string, Envelope> }) {
  switch (event.type) {
    case 'DetectionRaised':
    case 'DetectionUpdated': {
      const p = event.payload as unknown as Detection
      const updated = event.type === 'DetectionUpdated'
      return (
        <article className="flex flex-col gap-1 rounded-md border border-dashed border-border bg-muted/60 px-3 py-2">
          <Who label={updated ? 'DETECTOR · UPDATE' : 'DETECTOR'} className="text-muted-foreground" t={event.sim_time} />
          <p className="text-sm text-foreground">
            <span className="mr-1.5 font-mono text-xs font-medium">{p.rule}</span>
            <span className={cn('mr-1.5 rounded-sm px-1.5 py-px text-[10px] font-medium', SEVERITY_CLASS[p.severity])}>{updated ? `rises to ${SEVERITY_LABEL[p.severity]}` : SEVERITY_LABEL[p.severity]}</span>
            {p.message}
            {p.source && <span className="text-muted-foreground"> · source {SOURCE_LABEL[p.source]}</span>}
          </p>
          <span className="font-mono text-[10px] text-muted-foreground">{p.detection_id}</span>
        </article>
      )
    }
    case 'DetectionCleared': {
      const p = event.payload as unknown as DetectionCleared
      return (
        <article className="flex flex-col gap-1 rounded-md border border-dashed border-border bg-muted/60 px-3 py-2">
          <Who label="DETECTOR · CLEARED" className="text-muted-foreground" t={event.sim_time} />
          <p className="text-sm text-foreground">
            <span className="mr-1.5 font-mono text-xs font-medium">{p.rule}</span>
            {p.detection_id} cleared after {p.duration_s.toFixed(0)} s (maximum {p.max_value.toFixed(1)})
          </p>
        </article>
      )
    }
    case 'AnomalyDetected':
      return <AlertCard event={event as Envelope<Anomaly>} data={data} byId={byId} />
    case 'AlertClosed': {
      const p = event.payload as unknown as AlertClosed
      const ep = data.alerts.get(p.alert_id)?.episode
      return (
        <article className="flex flex-col gap-1 pl-3">
          <Who label="MONITOR · CLOSURE" className="text-primary" t={event.sim_time} />
          <p className="text-sm text-foreground">
            Closes alert <span className="font-mono">{p.alert_id}</span>
            {ep && <span className="font-mono text-muted-foreground"> ({ep})</span>}: {stripFieldValues(p.reason)}
          </p>
        </article>
      )
    }
    case 'DetectionAcknowledged': {
      const p = event.payload as unknown as DetectionAcknowledged
      const ep = p.alert_id ? data.alerts.get(p.alert_id)?.episode : null
      const text = p.fallback ? 'no diagnosis (the agent did not conclude)' : p.alert_id ? `alert ${p.alert_id} continues${ep ? ` (${ep})` : ''}` : 'no alert'
      return (
        <article className="flex flex-col gap-1 pl-3">
          <Who label="MONITOR · ACKNOWLEDGES" className="text-primary" t={event.sim_time} />
          <p className="text-sm text-foreground">
            <span className="font-mono text-xs">{p.detection_id}</span> <ArrowRight className="inline size-3" aria-hidden="true" /> <strong className="font-medium">{text}</strong>
            <span className="text-muted-foreground"> · {stripFieldValues(p.reason)}</span>
          </p>
        </article>
      )
    }
    default:
      return null
  }
}

function AlertCard({ event, data, byId }: { event: Envelope<Anomaly>; data: Derived; byId: Map<string, Envelope> }) {
  const a = event.payload
  const view = data.alerts.get(a.alert_id)
  const responds = event.causation_id ? byId.get(event.causation_id) : undefined
  const respondsTo = responds ? (responds.payload as { detection_id: string }).detection_id : event.causation_id
  return (
    <article className="flex flex-col gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-2" data-testid="alert-card">
      <Who label="MONITOR · ALERT" className="text-primary" t={event.sim_time} />
      <div className="flex flex-wrap items-center gap-1.5 text-sm">
        {view && <span className="rounded-sm bg-foreground px-1.5 py-px font-mono text-[10px] font-medium text-background">{view.episode}</span>}
        <span className="font-mono text-xs">{a.alert_id}</span>
        <strong className="font-medium">{CAUSE_LABEL[a.cause]}</strong>
        <span className={cn('rounded-sm px-1.5 py-px text-[10px] font-medium', SEVERITY_CLASS[a.severity])}>{SEVERITY_LABEL[a.severity]}</span>
        <span className="text-xs text-muted-foreground">confidence {(a.confidence * 100).toFixed(0)} %</span>
        {a.fallback && <span className="rounded-sm bg-muted px-1.5 py-px text-[10px] font-medium text-muted-foreground">fallback: no diagnosis</span>}
      </div>
      {a.supersedes && (
        <p className="flex items-center gap-1 text-xs font-medium text-primary" data-testid="supersedes">
          <Repeat2 className="size-3.5" aria-hidden="true" />
          Supersedes {a.supersedes} (same alert, {view?.episode})
        </p>
      )}
      <p className="text-sm leading-relaxed text-foreground text-pretty">{a.summary}</p>
      <details className="group text-sm">
        <summary className="cursor-pointer list-none text-xs font-medium text-primary [&::-webkit-details-marker]:hidden">
          <span className="mr-1 inline-block transition-transform group-open:rotate-90">›</span>
          Reasoning, checks and evidence
        </summary>
        <div className="mt-2 flex flex-col gap-2">
          <Section title="Explanation">{stripFieldValues(a.explanation)}</Section>
          <Section title="Recommendation">{stripFieldValues(a.recommendation)}</Section>
          <div>
            <h4 className="mb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Checks</h4>
            {a.checks ? (
              <ul className="grid gap-0.5 text-xs" data-testid="checks">
                {Object.entries(a.checks).map(([key, value]) => (
                  <li key={key} className="flex items-center gap-2">
                    <span className={cn('w-8 shrink-0 rounded-sm px-1 text-center font-mono text-[10px] font-medium', value === true ? 'bg-primary/15 text-primary' : value === false ? 'bg-muted text-muted-foreground' : 'bg-muted/60 text-muted-foreground')}>
                      {value === true ? 'yes' : value === false ? 'no' : '—'}
                    </span>
                    <span className="text-foreground">{CHECK_LABEL[key] ?? key}</span>
                    {value === null && <span className="text-muted-foreground">(not checked)</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No checks (fallback alert).</p>
            )}
          </div>
          <Section title="Evidence">
            <span className="font-mono text-xs">{a.evidence_event_ids.join(', ') || 'none'}</span>
          </Section>
          <p className="font-mono text-[10px] text-muted-foreground">
            responds to {respondsTo ?? '—'} · detections {a.detection_ids.join(', ')} · data up to {formatT(a.as_of_sim_time)}
          </p>
        </div>
      </details>
    </article>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{title}</h4>
      <p className="text-sm leading-relaxed text-foreground text-pretty">{children}</p>
    </div>
  )
}
