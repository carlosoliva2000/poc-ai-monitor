'use client'

import { ArrowUp, ChevronDown, ChevronUp } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useStoredState } from '@/hooks/use-stored-state'
import type { ChatEntry } from '@/lib/derive'
import { formatT } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ToolCallList } from './tool-calls'

const MIN_HEIGHT = 200 // cabecera + entrada de texto con las sugerencias + algo de conversación
const MAX_SHARE = 0.8 // del alto de la consola
const KEY_STEP = 24

type Saved = { height: number | null; minimized: boolean }
const DEFAULT_SAVED: Saved = { height: null, minimized: false }

function revive(raw: unknown): Saved {
  const r = (raw ?? {}) as Partial<Saved>
  return {
    height: typeof r.height === 'number' && Number.isFinite(r.height) && r.height >= MIN_HEIGHT ? r.height : null,
    minimized: r.minimized === true,
  }
}

type Props = {
  title: string
  agentLabel: string
  agentClass: string
  entries: ChatEntry[]
  suggestions: string[]
  placeholder: string
  onSend: (text: string) => boolean
  /** Muestra las llamadas a tool de cada respuesta (interruptor de la consola). */
  showToolCalls?: boolean
}

/** Chat con un agente: las respuestas llegan en streaming (trozos acumulados por el hook). */
export function ChatPanel({ title, agentLabel, agentClass, entries, suggestions, placeholder, onSend, showToolCalls = false }: Props) {
  const [input, setInput] = useState('')
  const [saved, setSaved] = useStoredState<Saved>(`poc-chat-${title}-v1`, DEFAULT_SAVED, revive)
  const [live, setLive] = useState<number | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const resize = useRef<{ y: number; height: number; max: number } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const last = entries[entries.length - 1]
  const waitingReply = last?.kind === 'operator'
  const lastLength = last && last.kind === 'agent' ? last.text.length : 0

  useEffect(() => {
    const el = scrollRef.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [entries.length, lastLength, waitingReply])

  const height = live ?? saved.height

  const clampHeight = (h: number, max: number) => Math.round(Math.min(Math.max(h, MIN_HEIGHT), Math.max(max, MIN_HEIGHT)))
  const maxHeight = () => (rootRef.current?.parentElement?.clientHeight ?? 800) * MAX_SHARE
  const onResizeDown = (e: React.PointerEvent) => {
    const root = rootRef.current
    if (!root) return
    resize.current = { y: e.clientY, height: root.offsetHeight, max: maxHeight() }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onResizeMove = (e: React.PointerEvent) => {
    const r = resize.current
    if (r) setLive(clampHeight(r.height + (r.y - e.clientY), r.max))
  }
  const onResizeEnd = () => {
    resize.current = null
    if (live !== null) setSaved((prev) => ({ ...prev, height: live }))
    setLive(null)
  }
  const onResizeKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    e.preventDefault()
    const current = height ?? rootRef.current?.offsetHeight ?? 240
    const next = clampHeight(current + (e.key === 'ArrowUp' ? KEY_STEP : -KEY_STEP), maxHeight())
    setSaved((prev) => ({ ...prev, height: next }))
  }

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    stick.current = true
    if (onSend(trimmed)) setInput('')
  }

  if (saved.minimized) {
    return (
      <div className="flex shrink-0 items-center justify-between border-t border-border bg-card px-4 py-1.5" data-testid={`chat-${title}`} data-minimized="true">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Chat · {title}</span>
        <button type="button" onClick={() => setSaved((prev) => ({ ...prev, minimized: false }))} aria-label={`Expand the ${title} chat`} aria-expanded={false} className="rounded-sm p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">
          <ChevronUp className="size-4" aria-hidden="true" />
        </button>
      </div>
    )
  }

  return (
    <div
      ref={rootRef}
      className={cn('relative flex min-h-0 flex-col overflow-hidden border-t border-border', height === null ? 'min-h-60 flex-1' : 'shrink-0')}
      style={height === null ? undefined : { height }}
      data-testid={`chat-${title}`}
      data-minimized="false"
    >
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label={`Resize the ${title} chat`}
        aria-valuenow={height ?? undefined}
        aria-valuemin={MIN_HEIGHT}
        tabIndex={0}
        onPointerDown={onResizeDown}
        onPointerMove={onResizeMove}
        onPointerUp={onResizeEnd}
        onPointerCancel={onResizeEnd}
        onKeyDown={onResizeKey}
        className="relative -mt-1 h-2 shrink-0 cursor-row-resize touch-none after:absolute after:left-1/2 after:top-1/2 after:h-0.5 after:w-8 after:-translate-x-1/2 after:-translate-y-1/2 after:rounded-full after:bg-border hover:bg-primary/20 focus-visible:bg-primary/30 focus-visible:outline-none"
        data-testid={`chat-${title}-resize`}
      />
      <div className="relative z-10 flex items-center justify-between bg-card px-4 pb-1 pt-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <span>Chat · {title}</span>
        <button type="button" onClick={() => setSaved((prev) => ({ ...prev, minimized: true }))} aria-label={`Minimize the ${title} chat`} aria-expanded={true} className="rounded-sm p-0.5 hover:bg-muted hover:text-foreground">
          <ChevronDown className="size-4" aria-hidden="true" />
        </button>
      </div>
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-2"
        role="log"
        aria-live="polite"
      >
        {entries.length === 0 && <p className="m-auto max-w-72 text-center text-xs leading-relaxed text-muted-foreground">Ask as the operator. The agent answers with what it knows up to the current instant of the simulation.</p>}
        {entries.map((m) =>
          m.kind === 'operator' ? (
            <article key={m.key} className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                <span className="tabular-nums">{formatT(m.t)}</span>
                <span className="font-medium text-accent">OPERATOR</span>
              </div>
              <p className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-tr-sm bg-foreground px-3 py-2 text-sm leading-relaxed text-background">{m.text}</p>
            </article>
          ) : (
            <article key={m.key} className="flex flex-col gap-1 pl-3">
              <span className={cn('font-mono text-[11px] font-medium', agentClass)}>{agentLabel} → OPERATOR</span>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground text-pretty">
                {m.text}
                {m.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-primary align-text-bottom" aria-hidden="true" />}
              </p>
              {showToolCalls && m.calls.length > 0 ? (
                <ToolCallList calls={m.calls} title={`Tool calls (${m.calls.length})`} />
              ) : m.toolCalls.length > 0 ? (
                <span className="font-mono text-[10px] text-muted-foreground">tools: {m.toolCalls.join(', ')}</span>
              ) : showToolCalls && !m.streaming ? (
                <span className="font-mono text-[10px] text-muted-foreground">no tool calls</span>
              ) : null}
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

      <div className="flex shrink-0 flex-col gap-2 p-3 pt-1">
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
            Operator message to {title}
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
          <Button type="submit" size="icon" disabled={!input.trim()} aria-label="Send">
            <ArrowUp aria-hidden="true" />
          </Button>
        </form>
      </div>
    </div>
  )
}

export function TypingDots() {
  return (
    <span className="flex gap-1" aria-label="Working">
      {[0, 150, 300].map((delay) => (
        <span key={delay} className="size-1.5 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: `${delay}ms` }} />
      ))}
    </span>
  )
}
