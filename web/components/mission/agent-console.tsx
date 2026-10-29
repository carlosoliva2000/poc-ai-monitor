'use client'

import { Hourglass } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useState } from 'react'
import { useStoredState } from '@/hooks/use-stored-state'
import type { ReportPhase } from '@/hooks/use-platform'
import type { AgentActivity, Conversation, Envelope } from '@/lib/contracts'
import { chatEntries, type Derived, type ToolCallEvent } from '@/lib/derive'
import { formatT } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ChatPanel, TypingDots } from './chat-panel'
import { MonitorFeed } from './monitor-feed'

type Tab = 'monitor' | 'report'

const TABS: { id: Tab; label: string }[] = [
  { id: 'monitor', label: 'Monitor' },
  { id: 'report', label: 'Report' },
]

const MONITOR_SUGGESTIONS = ['What is happening right now?', 'Why do you think that is the cause?', 'Which alerts are open?']
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
}

export function AgentConsole({ events, data, chunks, activity, toolCalls, reportPhase, finished, onSend }: Props) {
  const [tab, setTab] = useState<Tab>('monitor')
  const [showCalls, setShowCalls] = useStoredState<boolean>('poc-toolcalls-v1', true, (raw) => raw !== false)
  const calls = showCalls ? toolCalls : []
  const writing = reportPhase === 'writing' && !data.report

  return (
    <section aria-labelledby="agent-title" className="flex h-full min-h-0 flex-col bg-card">
      <header className="flex flex-col gap-3 border-b border-border px-4 pt-3">
        <div className="flex items-center justify-between gap-3">
          <h2 id="agent-title" className="text-sm font-semibold text-foreground">
            Agent console
          </h2>
          <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-label="Who is speaking">
            <Legend className="bg-muted-foreground" label="Detector" />
            <Legend className="bg-primary" label="Monitor" />
            <Legend className="bg-[oklch(0.55_0.12_195)]" label="Report" />
            <Legend className="bg-accent" label="Operator" />
          </div>
        </div>
        <div className="-mb-px flex items-end justify-between gap-4">
          <div role="tablist" aria-label="Agent" className="flex gap-4">
            {TABS.map((t) => (
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
          <MonitorFeed events={events} data={data} activity={activity} toolCalls={calls} />
          <ChatPanel
            title="monitor"
            agentLabel="MONITOR"
            agentClass="text-primary"
            entries={chatEntries(events, 'monitor', chunks, calls)}
            suggestions={MONITOR_SUGGESTIONS}
            placeholder="Ask the monitor…"
            onSend={(text) => onSend('monitor', text)}
            showToolCalls={showCalls}
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
                  Report generated · {formatT(data.report.sim_time)} · {data.report.payload.alerts_count} {data.report.payload.alerts_count === 1 ? 'alert' : 'alerts'}
                </p>
                <div className="md-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.report.payload.markdown}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <ReportNotice phase={reportPhase} finished={finished} />
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
        ? 'The simulation has finished. The report agent starts when the monitor has answered every detection.'
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
