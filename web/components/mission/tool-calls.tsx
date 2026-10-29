'use client'

import type { ToolCallStatus } from '@/lib/contracts'
import type { ToolCallEvent } from '@/lib/derive'
import { cn } from '@/lib/utils'

const STATUS_CLASS: Record<ToolCallStatus, string> = {
  ok: 'bg-primary/10 text-primary',
  error: 'bg-destructive text-destructive-foreground',
  rejected: 'bg-warning/20 text-foreground',
  aborted: 'bg-destructive text-destructive-foreground',
}
const STATUS_LABEL: Record<ToolCallStatus, string> = { ok: 'ok', error: 'error', rejected: 'rejected', aborted: 'aborted' }

/** JSON con sangría si se puede (si estaba recortado no es JSON válido: tal cual). */
export function prettyJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

/**
 * Desplegable con las llamadas a tool de una invocación o de una respuesta, en orden: nombre,
 * argumentos y resultado (o el error / rechazo del guardrail). Solo para depurar.
 */
export function ToolCallList({ calls, title, empty }: { calls: ToolCallEvent[]; title: string; empty?: string }) {
  if (calls.length === 0) {
    return empty ? <p className="font-mono text-[10px] text-muted-foreground">{empty}</p> : null
  }
  return (
    <details className="group text-xs" data-testid="tool-calls">
      <summary className="cursor-pointer list-none font-mono text-[11px] font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <span className="mr-1 inline-block transition-transform group-open:rotate-90">›</span>
        {title}
      </summary>
      <ol className="mt-1.5 flex flex-col gap-1.5 border-l border-border pl-3">
        {calls.map((c) => (
          <li key={c.event_id}>
            <details className="group/call rounded-md border border-border bg-muted/50">
              <summary className="flex cursor-pointer list-none items-center gap-2 px-2 py-1 font-mono text-[11px] [&::-webkit-details-marker]:hidden">
                <span className="text-muted-foreground">#{c.payload.index}</span>
                <span className="font-medium text-foreground">{c.payload.tool}</span>
                <span className={cn('rounded-sm px-1 py-px text-[10px] font-medium', STATUS_CLASS[c.payload.status])}>{STATUS_LABEL[c.payload.status]}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{c.payload.arguments}</span>
              </summary>
              <div className="flex flex-col gap-1.5 border-t border-border px-2 py-1.5">
                <Block label="Arguments" text={prettyJson(c.payload.arguments) || '(none)'} />
                {c.payload.error && <Block label={c.payload.status === 'rejected' ? 'Rejected' : 'Error'} text={c.payload.error} danger />}
                {c.payload.result !== null && <Block label="Result" text={prettyJson(c.payload.result)} />}
                {c.payload.truncated && <p className="text-[10px] italic text-muted-foreground">Shortened for display.</p>}
              </div>
            </details>
          </li>
        ))}
      </ol>
    </details>
  )
}

function Block({ label, text, danger = false }: { label: string; text: string; danger?: boolean }) {
  return (
    <div>
      <h5 className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</h5>
      <pre className={cn('max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-sm bg-card px-2 py-1 font-mono text-[11px] leading-snug', danger ? 'text-destructive' : 'text-foreground')}>{text}</pre>
    </div>
  )
}
