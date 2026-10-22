'use client'

import { ArrowUp } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { ChatEntry } from '@/lib/derive'
import { formatT } from '@/lib/format'
import { cn } from '@/lib/utils'

type Props = {
  title: string
  agentLabel: string
  agentClass: string
  entries: ChatEntry[]
  suggestions: string[]
  placeholder: string
  onSend: (text: string) => boolean
}

/** Chat con un agente: las respuestas llegan en streaming (trozos acumulados por el hook). */
export function ChatPanel({ title, agentLabel, agentClass, entries, suggestions, placeholder, onSend }: Props) {
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const last = entries[entries.length - 1]
  const waitingReply = last?.kind === 'operator'
  const lastLength = last && last.kind === 'agent' ? last.text.length : 0

  useEffect(() => {
    const el = scrollRef.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [entries.length, lastLength, waitingReply])

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    stick.current = true
    if (onSend(trimmed)) setInput('')
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col border-t border-border" data-testid={`chat-${title}`}>
      <div className="relative z-10 flex items-center justify-between bg-card px-4 pb-1 pt-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <span>Chat · {title}</span>
      </div>
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}
        className="flex min-h-24 flex-1 flex-col gap-3 overflow-y-auto px-4 py-2"
        role="log"
        aria-live="polite"
      >
        {entries.length === 0 && <p className="m-auto max-w-72 text-center text-xs leading-relaxed text-muted-foreground">Pregunta como operador. El agente contesta con lo que sabe hasta el instante actual de la simulación.</p>}
        {entries.map((m) =>
          m.kind === 'operator' ? (
            <article key={m.key} className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                <span className="tabular-nums">{formatT(m.t)}</span>
                <span className="font-medium text-accent">OPERADOR</span>
              </div>
              <p className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-tr-sm bg-foreground px-3 py-2 text-sm leading-relaxed text-background">{m.text}</p>
            </article>
          ) : (
            <article key={m.key} className="flex flex-col gap-1 pl-3">
              <span className={cn('font-mono text-[11px] font-medium', agentClass)}>{agentLabel} → OPERADOR</span>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground text-pretty">
                {m.text}
                {m.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-text-bottom" aria-hidden="true" />}
              </p>
              {m.toolCalls.length > 0 && <span className="font-mono text-[10px] text-muted-foreground">tools: {m.toolCalls.join(', ')}</span>}
            </article>
          ),
        )}
        {waitingReply && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className={cn('font-mono font-medium', agentClass)}>{agentLabel}</span>
            <TypingDots />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2 p-3 pt-1">
        {entries.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => submit(s)}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit(input)
          }}
          className="flex items-end gap-2 rounded-lg border border-input bg-background p-2 focus-within:border-ring"
        >
          <label htmlFor={`input-${title}`} className="sr-only">
            Mensaje del operador a {title}
          </label>
          <textarea
            id={`input-${title}`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                if (e.nativeEvent.isComposing || e.keyCode === 229) return
                e.preventDefault()
                submit(input)
              }
            }}
            rows={2}
            placeholder={placeholder}
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-1 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
          />
          <Button type="submit" size="icon" disabled={!input.trim()} aria-label="Enviar">
            <ArrowUp aria-hidden="true" />
          </Button>
        </form>
      </div>
    </div>
  )
}

export function TypingDots() {
  return (
    <span className="flex gap-1" aria-label="Procesando">
      {[0, 150, 300].map((delay) => (
        <span key={delay} className="size-1.5 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: `${delay}ms` }} />
      ))}
    </span>
  )
}
