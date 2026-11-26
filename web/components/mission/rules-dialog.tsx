'use client'

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import frozen from '@/lib/situation-tables-frozen.json'
import handwritten from '@/lib/situation-tables.json'
import { pickRules, rulesView, type RulesFile } from '@/lib/rules'
import { cn } from '@/lib/utils'

type Props = {
  /** Faceta de la evidencia (`gps.integrity`…) y fila que encajó. */
  facet: string
  matched: string
  /** El juego de tablas que ejecutó el monitor (`IncidentUpdated.table`). */
  table: string
  onClose: () => void
}

/**
 * Ventana de solo lectura con las reglas completas de una faceta, en el orden en que se evalúan, y
 * la fila que encajó resaltada. Salen de `situation-tables-frozen.json` (las tablas congeladas, con la
 * regla de la situación) o, si el monitor corre con las del vídeo, de `situation-tables.json`; los dos
 * se generan de los ficheros que ejecuta el monitor: no hay copia a mano. Sin edición.
 */
export function RulesDialog({ facet, matched, table, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const view = rulesView(pickRules(table, frozen as unknown as RulesFile, handwritten as unknown as RulesFile), facet, matched)
  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    dialog?.querySelector('[data-matched="true"]')?.scrollIntoView({ block: 'center' })
  }, [])
  if (!view) return null
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      aria-labelledby="rules-title"
      data-testid="rules-dialog"
      className="m-auto max-h-[82dvh] w-[min(48rem,94vw)] overflow-hidden rounded-lg border border-border bg-card p-0 text-foreground shadow-xl backdrop:bg-foreground/40"
    >
      <div className="flex max-h-[82dvh] flex-col">
        <header className="flex items-start gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 id="rules-title" className="text-sm font-semibold">
              Rules · {view.title}
            </h2>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{view.description}</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Read only · hit policy <strong className="font-mono font-medium text-foreground">{view.policy}</strong>: the rows are checked in order and the first one that matches decides.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>
        <ol className="flex flex-col gap-1.5 overflow-y-auto px-4 py-3" data-testid="rules-list">
          {view.lines.map((line, i) => (
            <li
              key={line.id}
              data-matched={line.matched}
              className={cn('rounded-md border px-3 py-2 text-xs', line.matched ? 'border-primary bg-primary/10' : 'border-border bg-background/60')}
            >
              <div className="flex items-baseline gap-2">
                <span className="w-4 shrink-0 text-right font-mono text-[10px] text-muted-foreground">{i + 1}</span>
                <span className="font-mono font-medium">{line.id}</span>
                {line.matched && <span className="rounded-sm bg-primary px-1.5 py-px text-[10px] font-medium text-primary-foreground">matched</span>}
                <span className="ml-auto text-muted-foreground">then</span>
                <strong className="font-medium" data-testid="rule-output" title={line.support ?? undefined}>{line.output}</strong>
              </div>
              <ul className="mt-1 pl-6 font-mono text-[11px] leading-snug text-muted-foreground">
                {line.conditions.length === 0 ? <li>otherwise</li> : line.conditions.map((c) => <li key={c}>{c}</li>)}
              </ul>
              {line.note && <p className="mt-1 pl-6 text-[11px] italic leading-snug text-muted-foreground">{line.note}</p>}
            </li>
          ))}
        </ol>
      </div>
    </dialog>
  )
}
