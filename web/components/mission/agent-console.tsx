'use client'

import { Hourglass } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useMemo, useState } from 'react'
import { useStoredState } from '@/hooks/use-stored-state'
import type { ReportPhase } from '@/hooks/use-platform'
import type { AgentActivity, Conversation, Envelope, Proposal } from '@/lib/contracts'
import { chatEntries, type Derived, type ToolCallEvent } from '@/lib/derive'
import { formatT } from '@/lib/format'
import type { View } from '@/lib/view'
import { splitReport } from '@/lib/report'
import { cn } from '@/lib/utils'
import { ChatPanel, TypingDots } from './chat-panel'
import { IncidentList } from './incident-list'
import { MonitorFeed } from './monitor-feed'
import { ProposalCard, type Decision } from './proposal-card'

type Tab = 'monitor' | 'report' | 'instructor'

const TABS: { id: Tab; label: string }[] = [
  { id: 'monitor', label: 'Monitor' },
  { id: 'report', label: 'Report' },
  { id: 'instructor', label: 'Instructor' },
]

const MONITOR_SUGGESTIONS = ['What is happening right now?', 'Why do you think that is the cause?', 'Which alerts are open?']
/** Con un secuestro en el ejercicio, la pregunta que lo cuestiona va la primera. */
const HIJACK_QUESTION = 'Why do you think the drone is being hijacked?'
const INSTRUCTOR_SUGGESTIONS = ['Put a strong wind from the north, 19 m/s, until I cancel it', 'Remove the wind', 'Wind from the north-east at 8 m/s', 'Put a 12 m/s wind from the north for one minute']
const REPORT_SUGGESTIONS = ['What happened during the flight?', 'Which was the most serious anomaly?', 'What do you recommend?']

type Props = {
  events: Envelope[]
  data: Derived
  chunks: Record<string, string>
  activity: Record<string, AgentActivity>
  toolCalls: ToolCallEvent[]
  reportPhase: ReportPhase
  /** La simulación ha terminado (el informe lo escribe el agente a continuación). */
  finished: boolean
  onSend: (conversation: Conversation, text: string) => boolean
  /** Modo interactivo encendido: sin él no se puede confirmar una propuesta. */
  interactive: boolean
  onConfirmProposal: (proposal: Proposal, text: string) => void
  onEditProposal: (proposal: Proposal) => void
  /** Vista del alumno: sin la pestaña del instructor. */
  view?: View
  /** Instante actual de la simulación (cuánto lleva abierto cada incidente). */
  simTime?: number
}

export function AgentConsole({ events, data, chunks, activity, toolCalls, reportPhase, finished, onSend, interactive, onConfirmProposal, onEditProposal, view = 'instructor', simTime = 0 }: Props) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>({})
  const [selected, setTab] = useState<Tab>('monitor')
  const tabs = view === 'student' ? TABS.filter((t) => t.id !== 'instructor') : TABS
  const tab: Tab = tabs.some((t) => t.id === selected) ? selected : 'monitor'
  const [showCalls, setShowCalls] = useStoredState<boolean>('poc-toolcalls-v1', true, (raw) => raw !== false)
  const calls = showCalls ? toolCalls : []
  const writing = reportPhase === 'writing' && !data.report
  // El monitor de situación publica incidentes; las ejecuciones con el detector y las alertas
  // (módulo anterior) se siguen viendo con su lista de avisos.
  const legacy = useMemo(() => events.some((e) => e.source === 'ai-detector' || e.type === 'AnomalyDetected'), [events])
  const hijack = useMemo(() => events.some((e) => e.type === 'IncidentUpdated' && (e.payload as { kind?: string }).kind === 'HIJACK'), [events])
  const incidentRun = useMemo(() => events.some((e) => e.type === 'IncidentUpdated'), [events])
  const monitorSuggestions = hijack ? [HIJACK_QUESTION, ...MONITOR_SUGGESTIONS] : MONITOR_SUGGESTIONS

  return (
    <section aria-labelledby="agent-title" className="flex h-full min-h-0 flex-col bg-card">
      <header className="flex flex-col gap-3 border-b border-border px-4 pt-3">
        <div className="flex items-center justify-between gap-3">
          <h2 id="agent-title" className="text-sm font-semibold text-foreground">
            Agent console
          </h2>
          <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-label="Who is speaking">
            <Legend className="bg-primary" label="Monitor" />
            <Legend className="bg-[oklch(0.55_0.12_195)]" label="Report" />
            <Legend className="bg-accent" label="Operator" />
          </div>
        </div>
        <div className="-mb-px flex items-end justify-between gap-4">
          <div role="tablist" aria-label="Agent" className="flex gap-4">
            {tabs.map((t) => (
              <button
                key={t.id}
                role="tab"
                type="button"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  'border-b-2 pb-2 text-sm font-medium transition-colors',
                  tab === t.id ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {t.label}
                {t.id === 'monitor' && data.pending.length > 0 && <span className="ml-1.5 inline-block size-1.5 animate-pulse rounded-full bg-accent align-middle" aria-hidden="true" />}
                {t.id === 'report' && writing && <span className="ml-1.5 inline-block size-1.5 animate-pulse rounded-full bg-accent align-middle" aria-hidden="true" />}
                {t.id === 'report' && data.report && <span className="ml-1.5 inline-block size-1.5 rounded-full bg-primary align-middle" aria-hidden="true" />}
              </button>
            ))}
          </div>
          <label className="mb-2 flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground" title="Show each tool call of the agents (name, arguments and result)">
            <input type="checkbox" role="switch" checked={showCalls} onChange={(e) => setShowCalls(e.target.checked)} className="size-3 accent-primary" />
            Tool calls
          </label>
        </div>
      </header>

      {tab === 'monitor' ? (
        <>
          {legacy ? <MonitorFeed events={events} data={data} activity={activity} toolCalls={calls} /> : <IncidentList events={events} simTime={simTime} />}
          <ChatPanel
            title="monitor"
            agentLabel="MONITOR"
            agentClass="text-primary"
            entries={chatEntries(events, 'monitor', chunks, calls)}
            suggestions={monitorSuggestions}
            placeholder="Ask the monitor…"
            onSend={(text) => onSend('monitor', text)}
            showToolCalls={showCalls}
          />
        </>
      ) : tab === 'instructor' ? (
        <>
          <p className="px-4 py-3 text-xs leading-relaxed text-muted-foreground" data-testid="instructor-intro">
            Tell the instructor assistant, in English and in m/s, what wind to put on the drone. It only proposes: nothing is applied until you confirm. The monitor is not told.
          </p>
          <ChatPanel
            title="instructor"
            agentLabel="INSTRUCTOR"
            agentClass="text-accent"
            entries={chatEntries(events, 'instructor', chunks, calls)}
            suggestions={INSTRUCTOR_SUGGESTIONS}
            placeholder="e.g. Wind from the north at 12 m/s…"
            onSend={(text) => onSend('instructor', text)}
            showToolCalls={showCalls}
            extra={(m) =>
              m.proposal && m.replyTo ? (
                <ProposalCard
                  proposal={m.proposal}
                  decision={decisions[m.replyTo]}
                  canConfirm={interactive}
                  onConfirm={() => {
                    setDecisions((d) => ({ ...d, [m.replyTo as string]: 'confirmed' }))
                    onConfirmProposal(m.proposal as Proposal, m.question ?? '')
                  }}
                  onEdit={() => onEditProposal(m.proposal as Proposal)}
                  onDiscard={() => setDecisions((d) => ({ ...d, [m.replyTo as string]: 'discarded' }))}
                />
              ) : null
            }
          />
        </>
      ) : (
        <>
          <div className="min-h-24 flex-[3] overflow-y-auto px-4 py-3" data-testid="report-view">
            {data.report ? (
              <div className="flex flex-col gap-3">
                <p
                  role="status"
                  className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 font-mono text-xs text-foreground"
                  data-testid="report-done"
                >
                  Report generated · {formatT(data.report.sim_time)} · {data.report.payload.alerts_count} {noun(data.report.payload.alerts_count, incidentRun)}
                </p>
                <ReportBody markdown={data.report.payload.markdown} />
              </div>
            ) : (
              <ReportNotice phase={reportPhase} finished={finished} />
            )}
            {view === 'instructor' && data.debrief && (
              <details open className="mt-3 rounded-md border border-warning/40 bg-warning/5 px-3 py-2" data-testid="debrief">
                <summary className="cursor-pointer select-none font-mono text-xs text-muted-foreground">
                  Instructor debriefing · {formatT(data.debrief.sim_time)} · {data.debrief.payload.injects_count} injected
                </summary>
                <div className="md-body mt-2">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.debrief.payload.markdown}</ReactMarkdown>
                </div>
              </details>
            )}
          </div>
          {data.report && (
            <ChatPanel
              title="report"
              agentLabel="REPORT"
              agentClass="text-[oklch(0.45_0.12_195)]"
              entries={chatEntries(events, 'report', chunks, calls)}
              suggestions={REPORT_SUGGESTIONS}
              placeholder="Ask the report agent…"
              onSend={(text) => onSend('report', text)}
              showToolCalls={showCalls}
            />
          )}
        </>
      )}
    </section>
  )
}

/** Qué decir en la pestaña Informe mientras no hay informe. */
/** Informe de misión y, plegada, la autoevaluación técnica del monitor (anexo). */
/** «3 incidents» si el monitor publicó incidentes; «3 alerts» con el módulo anterior. */
const noun = (n: number, incidents: boolean) => (incidents ? (n === 1 ? 'incident' : 'incidents') : n === 1 ? 'alert' : 'alerts')

function ReportBody({ markdown }: { markdown: string }) {
  const { mission, annex, annexTitle } = splitReport(markdown)
  return (
    <>
      <div className="md-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{mission}</ReactMarkdown>
      </div>
      {annex && (
        <details className="rounded-md border border-border bg-muted/30 px-3 py-2" data-testid="report-annex">
          <summary className="cursor-pointer select-none font-mono text-xs text-muted-foreground">{annexTitle}</summary>
          <div className="md-body mt-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{annex}</ReactMarkdown>
          </div>
        </details>
      )}
    </>
  )
}

function ReportNotice({ phase, finished }: { phase: ReportPhase; finished: boolean }) {
  if (phase === 'writing') {
    return (
      <div role="status" className="flex items-center gap-2 rounded-md border border-accent/50 bg-accent/10 px-3 py-2 text-sm text-foreground" data-testid="report-writing">
        <Hourglass className="size-4 shrink-0 animate-pulse text-accent" aria-hidden="true" />
        <span>The report agent is writing the report…</span>
        <TypingDots />
      </div>
    )
  }
  const text =
    phase === 'finished'
      ? 'The report agent finished without publishing a report.'
      : finished
        ? 'The simulation has finished and no report has been published for this run.'
        : 'The report is generated when the simulation ends. Until then nothing appears here.'
  return (
    <p role="status" className="m-auto max-w-72 pt-8 text-center text-sm leading-relaxed text-muted-foreground text-pretty" data-testid="report-notice">
      {text}
    </p>
  )
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('size-2 rounded-sm', className)} aria-hidden="true" />
      {label}
    </span>
  )
}
