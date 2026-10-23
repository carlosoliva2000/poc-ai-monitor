'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AgentActivity, Conversation, Envelope } from '@/lib/contracts'
import { chatEntries, type Derived } from '@/lib/derive'
import { cn } from '@/lib/utils'
import { ChatPanel } from './chat-panel'
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
  onSend: (conversation: Conversation, text: string) => boolean
}

export function AgentConsole({ events, data, chunks, activity, onSend }: Props) {
  const [tab, setTab] = useState<Tab>('monitor')

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
        <div role="tablist" aria-label="Agent" className="-mb-px flex gap-4">
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
              {t.id === 'report' && data.report && <span className="ml-1.5 inline-block size-1.5 rounded-full bg-primary align-middle" aria-hidden="true" />}
            </button>
          ))}
        </div>
      </header>

      {tab === 'monitor' ? (
        <>
          <MonitorFeed events={events} data={data} activity={activity} />
          <ChatPanel
            title="monitor"
            agentLabel="MONITOR"
            agentClass="text-primary"
            entries={chatEntries(events, 'monitor', chunks)}
            suggestions={MONITOR_SUGGESTIONS}
            placeholder="Ask the monitor…"
            onSend={(text) => onSend('monitor', text)}
          />
        </>
      ) : (
        <>
          <div className="min-h-24 flex-[3] overflow-y-auto px-4 py-3" data-testid="report-view">
            {data.report ? (
              <div className="md-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.report.payload.markdown}</ReactMarkdown>
              </div>
            ) : (
              <p className="m-auto max-w-64 pt-8 text-center text-sm leading-relaxed text-muted-foreground text-pretty">
                The report agent writes the report when the simulation ends and the monitor has answered everything.
              </p>
            )}
          </div>
          <ChatPanel
            title="report"
            agentLabel="REPORT"
            agentClass="text-[oklch(0.45_0.12_195)]"
            entries={chatEntries(events, 'report', chunks)}
            suggestions={REPORT_SUGGESTIONS}
            placeholder="Ask the report agent…"
            onSend={(text) => onSend('report', text)}
          />
        </>
      )}
    </section>
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
