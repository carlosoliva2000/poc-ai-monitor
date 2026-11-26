'use client'

import { useState } from 'react'
import { formatT, SEVERITY_LABEL } from '@/lib/format'
import type { IncidentEnriched, IncidentState } from '@/lib/contracts'
import type { IncidentText, IncidentView } from '@/lib/derive'
import { CONFIDENCE_LABEL, CONFIDENCE_TITLE, describeContext, evidenceRows, formatDuration, KIND_LABEL, STATE_LABEL, type EvidenceRow } from '@/lib/incidents'
import type { EvidenceItem } from '@/lib/contracts'
import { cn } from '@/lib/utils'
import { TypingDots } from './chat-panel'
import { RulesDialog } from './rules-dialog'
import { SEVERITY_CLASS } from './monitor-feed'

const STATE_CLASS: Record<IncidentState, string> = {
  open: 'bg-destructive/10 text-destructive',
  recovering: 'bg-primary/10 text-primary',
  closed: 'bg-muted text-muted-foreground',
}

type Props = {
  incident: IncidentView
  /** Instante actual de la simulación: para cuánto lleva abierto. */
  simTime: number
}

/**
 * Una tarjeta por incidente (contrato v1.1): nombre, severidad, estado, desde cuándo, confianza,
 * evidencias (el camino de la tabla con su valor actual), qué comprobar y, aparte y marcada, la
 * interpretación del asistente. Un incidente cerrado se pliega: solo la cabecera.
 */
export function IncidentCard({ incident, simTime }: Props) {
  const [rules, setRules] = useState<{ facet: string; rule: string } | null>(null)
  const p = incident.latest.payload
  const closed = p.state === 'closed'
  const end = closed ? p.as_of_sim_time : Math.max(simTime, p.as_of_sim_time)
  const lasted = formatDuration(end - p.opened_at)
  // Por qué se abrió (y por qué cambió de nombre, si lo hizo): las evidencias de esas revisiones,
  // para el incidente que ya no está abierto, cuyas evidencias de ahora son las de la recuperación.
  const origin = p.state === 'open' ? [] : incident.revisions.filter((r) => r.payload.change === 'opened' || r.payload.change === 'renamed')
  const onRules = (facet: string, rule: string) => setRules({ facet, rule })

  const head = (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5 text-sm">
        <span className="font-mono text-xs text-muted-foreground">{incident.id}</span>
        <strong className="font-medium" data-testid="incident-name">{p.name}</strong>
        <span className={cn('rounded-sm px-1.5 py-px text-[10px] font-medium', SEVERITY_CLASS[p.severity])} title="Risk now: it goes down while recovering" data-testid="incident-severity">
          {SEVERITY_LABEL[p.severity]}
        </span>
        <span className={cn('rounded-sm px-1.5 py-px text-[10px] font-medium', STATE_CLASS[p.state])} data-testid="incident-state">
          {STATE_LABEL[p.state]}
        </span>
        <span className="rounded-sm border border-border px-1.5 py-px text-[10px] text-muted-foreground" title={CONFIDENCE_TITLE[p.confidence]} data-testid="incident-confidence">
          {CONFIDENCE_LABEL[p.confidence]}
        </span>
      </div>
      <p className="font-mono text-[11px] text-muted-foreground" data-testid="incident-since">
        Since {formatT(p.opened_at)} · {closed ? `lasted ${lasted}` : p.state === 'recovering' ? `${lasted} so far` : `open for ${lasted}`}
        {incident.path.length > 1 && <span data-testid="incident-path"> · {incident.path.join(' → ')}</span>}
      </p>
    </div>
  )

  const body = (
    <div className="mt-2 flex flex-col gap-2.5">
      <EvidenceBlock title={p.state === 'open' ? 'Evidence' : 'Evidence now'} asOf={p.as_of_sim_time} evidence={p.evidence} onRules={onRules} testId="incident-evidence" />
      {origin.map((r) => (
        <EvidenceBlock
          key={r.payload.revision}
          title={r.payload.change === 'opened' ? 'Why it opened' : `Why it became ${r.payload.name}`}
          asOf={r.payload.as_of_sim_time}
          evidence={r.payload.evidence}
          onRules={onRules}
          testId={r.payload.change === 'opened' ? 'incident-why-opened' : 'incident-why-renamed'}
        />
      ))}
      {p.context.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Context" data-testid="incident-context">
          {p.context.map((c) => (
            <li key={c.feature} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              {describeContext(c)}
            </li>
          ))}
        </ul>
      )}
      {!closed && p.checks.length > 0 && (
        <div data-testid="incident-checks">
          <h4 className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">What to check</h4>
          <ul className="list-disc pl-4 text-sm leading-relaxed text-foreground marker:text-muted-foreground">
            {p.checks.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <Interpretation text={incident.text} undetermined={p.kind === 'UNDETERMINED'} />
      <History incident={incident} />
    </div>
  )

  return (
    <article
      className={cn('rounded-md border px-3 py-2.5', closed ? 'border-border bg-muted/30' : p.state === 'recovering' ? 'border-primary/40 bg-primary/5' : 'border-destructive/40 bg-destructive/5')}
      data-testid="incident-card"
      data-incident={incident.id}
      data-kind={p.kind}
      data-subject={p.subject ?? undefined}
      data-state={p.state}
    >
      {closed ? (
        <details className="group">
          <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
            <div className="flex items-start gap-1.5">
              <span className="mt-0.5 inline-block text-xs text-muted-foreground transition-transform group-open:rotate-90" aria-hidden="true">›</span>
              <div className="min-w-0 flex-1">{head}</div>
            </div>
          </summary>
          {body}
        </details>
      ) : (
        <>
          {head}
          {body}
        </>
      )}
      {rules && <RulesDialog facet={rules.facet} matched={rules.rule} table={p.table} onClose={() => setRules(null)} />}
    </article>
  )
}

/** El camino que siguió el monitor: una línea por faceta con su estado, la fila que decidió y las
 *  condiciones con su valor en esa revisión. El botón «Rules» abre las reglas completas de la faceta. */
function EvidenceBlock({ title, asOf, evidence, onRules, testId }: { title: string; asOf: number; evidence: EvidenceItem[]; onRules: (facet: string, rule: string) => void; testId: string }) {
  const rows: EvidenceRow[] = evidenceRows(evidence)
  return (
    <div data-testid={testId}>
      <h4 className="mb-1 flex items-baseline gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {title}
        <span className="font-mono normal-case tracking-normal">as of {formatT(asOf)}</span>
      </h4>
      <ul className="flex flex-col gap-1.5">
        {rows.map((r) => (
          <li key={r.facetId} className="rounded-sm bg-background/70 px-2 py-1" data-testid="evidence-row">
            <div className="flex items-baseline gap-1.5 text-xs">
              <span className="text-muted-foreground">{r.facet}</span>
              <strong className="font-medium text-foreground">{r.state}</strong>
              <span className="ml-auto font-mono text-[10px] text-muted-foreground">{r.rule}</span>
              <button
                type="button"
                onClick={() => onRules(r.facetId, r.rule)}
                className="rounded border border-border px-1.5 py-px text-[10px] font-medium text-primary hover:bg-primary/10"
                title="See all the rules of this check"
                data-testid="rules-button"
              >
                Rules
              </button>
            </div>
            {r.conditions.length > 0 && (
              <ul className="mt-0.5 font-mono text-[11px] leading-snug text-muted-foreground">
                {r.conditions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Cada revisión del incidente (un evento por transición), para quien quiera auditar. */
function History({ incident }: { incident: IncidentView }) {
  return (
    <details className="group text-xs" data-testid="incident-history">
      <summary className="cursor-pointer list-none text-xs font-medium text-primary [&::-webkit-details-marker]:hidden">
        <span className="mr-1 inline-block transition-transform group-open:rotate-90">›</span>
        History ({incident.revisions.length} {incident.revisions.length === 1 ? 'revision' : 'revisions'})
      </summary>
      <ol className="mt-1 flex flex-col gap-0.5 font-mono text-[11px] text-muted-foreground">
        {incident.revisions.map((r) => (
          <li key={r.event_id}>
            {formatT(r.payload.as_of_sim_time)} · {r.payload.change === 'evidence' ? 'evidence updated' : r.payload.change} · {r.payload.name} · {r.payload.state} · {SEVERITY_LABEL[r.payload.severity]}
          </li>
        ))}
      </ol>
    </details>
  )
}

/** La interpretación del asistente, aparte y marcada: no es lo que decidió el incidente. */
function Interpretation({ text, undetermined }: { text: IncidentText; undetermined: boolean }) {
  if (text.state === 'none') return undetermined ? <NoHypothesis /> : null
  if (text.state === 'missed') {
    return (
      <div className="flex flex-col gap-1 border-l-2 border-muted-foreground/40 pl-2" data-testid="interpretation">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Interpretation (LLM)</span>
        <span className="text-xs text-muted-foreground" data-testid="interpretation-missed">No interpretation: the assistant did not answer in time.</span>
        {undetermined && <NoHypothesis />}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1 border-l-2 border-muted-foreground/40 pl-2" data-testid="interpretation">
      <span className="flex items-baseline gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        Interpretation (LLM)
        {text.state === 'published' && (
          <span className="font-mono normal-case tracking-normal" title="The interpretation was written for the update of this moment" data-testid="interpretation-as-of">
            for the {text.enrichment.state} update · {formatT(text.enrichment.as_of_sim_time)}
          </span>
        )}
      </span>
      {text.state === 'pending' ? (
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="interpretation-pending">
          pending…
          <TypingDots />
        </span>
      ) : (
        <>
          <p className="text-sm leading-relaxed text-foreground text-pretty" data-testid="interpretation-text">{text.enrichment.text}</p>
          {text.enrichment.hypothesis && <HypothesisBlock hypothesis={text.enrichment.hypothesis} />}
          {undetermined && !text.enrichment.hypothesis && <NoHypothesis />}
        </>
      )}
    </div>
  )
}

/** La hipótesis estructurada del asistente (v1.4): causas ordenadas, lo que las apoya, lo que falta
 *  y qué comprobar. Marcada como hipótesis: no es un diagnóstico. */
function HypothesisBlock({ hypothesis }: { hypothesis: NonNullable<IncidentEnriched['hypothesis']> }) {
  const ranked = hypothesis.ranked ?? []
  const checks = hypothesis.checks ?? []
  return (
    <div className="flex flex-col gap-1 rounded-sm bg-warning/15 px-1.5 py-1 text-xs text-foreground" data-testid="hypothesis">
      <span className="font-medium">Hypothesis (LLM, not a diagnosis)</span>
      {ranked.length === 0 ? (
        <span>{KIND_LABEL[hypothesis.kind]} · {hypothesis.confidence}</span>
      ) : (
        <ol className="list-decimal pl-4" data-testid="hypothesis-ranked">
          {ranked.map((c) => (
            <li key={c.kind}>
              <span className="font-medium">{KIND_LABEL[c.kind]}</span>
              {c.supports.length > 0 && <span> · supports: {c.supports.join('; ')}</span>}
              {c.missing.length > 0 && <span className="text-muted-foreground"> · missing: {c.missing.join('; ')}</span>}
            </li>
          ))}
        </ol>
      )}
      {checks.length > 0 && (
        <ul className="list-disc pl-4" data-testid="hypothesis-checks">
          {checks.map((c) => (
            <li key={`${c.target}-${c.text}`}><span className="font-mono">{c.target}</span>: {c.text}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** «Sin determinar» no tiene causa: la hipótesis queda vacía hasta que el asistente (LLM) pueda proponer una. */
function NoHypothesis() {
  return (
    <p className="rounded-sm bg-muted px-1.5 py-0.5 text-xs text-muted-foreground" data-testid="no-hypothesis">
      Hypothesis: none. The cause is not determined; nothing here is a diagnosis.
    </p>
  )
}
