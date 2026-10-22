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
  { id: 'report', label: 'Informe' },
]

const MONITOR_SUGGESTIONS = ['¿Qué está pasando ahora mismo?', '¿Por qué crees que es esa causa?', '¿Qué alertas hay abiertas?']
const REPORT_SUGGESTIONS = ['¿Qué pasó en el vuelo?', '¿Cuál fue la anomalía más grave?', '¿Qué recomiendas?']

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
            Consola del agente
          </h2>
          <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-label="Quién habla">
            <Legend className="bg-muted-foreground" label="Detector" />
            <Legend className="bg-primary" label="Monitor" />
            <Legend className="bg-[oklch(0.55_0.12_195)]" label="Informe" />
            <Legend className="bg-accent" label="Operador" />
          </div>
        </div>
        <div role="tablist" aria-label="Agente" className="-mb-px flex gap-4">
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
            placeholder="Pregunta al monitor…"
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
                El agente de informe escribe el informe cuando termina la simulación y el monitor ha respondido a todo.
              </p>
            )}
          </div>
          <ChatPanel
            title="informe"
            agentLabel="INFORME"
            agentClass="text-[oklch(0.45_0.12_195)]"
            entries={chatEntries(events, 'report', chunks)}
            suggestions={REPORT_SUGGESTIONS}
            placeholder="Pregunta al agente de informe…"
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
