'use client'

import { useMemo } from 'react'
import { ChevronDown, ScanEye } from 'lucide-react'
import { useStoredState } from '@/hooks/use-stored-state'
import type { Envelope, TruthFile } from '@/lib/contracts'
import { incidents } from '@/lib/derive'
import { formatT } from '@/lib/format'
import { injectedEpisodes, injectedVsDetected } from '@/lib/injected'
import { formatDuration } from '@/lib/incidents'
import { cn } from '@/lib/utils'

type Props = {
  events: Envelope[]
  /** La verdad del ejercicio (`/api/truth`): solo llega a la vista del instructor. */
  truth: TruthFile | null
}

/**
 * «Injected vs detected» (vista del instructor): qué se inyectó en el ejercicio y cuándo, y qué
 * incidente lo vio y con cuánto retraso. Sirve para evaluar el ejercicio. El monitor no ve nada
 * de esto: la verdad y los comandos del instructor no le llegan.
 */
export function InjectedPanel({ events, truth }: Props) {
  const [open, setOpen] = useStoredState<boolean>('poc-injected-open-v1', true, (raw) => raw !== false)
  const rows = useMemo(() => injectedVsDetected(injectedEpisodes(truth, events), incidents(events)), [truth, events])
  return (
    <section className="flex flex-col border-t border-border bg-card px-4 py-3" aria-labelledby="injected-title" data-testid="injected-panel">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-2 text-left">
        <ScanEye className="size-4 text-muted-foreground" aria-hidden="true" />
        <h2 id="injected-title" className="text-sm font-semibold text-foreground">Injected vs detected</h2>
        <span className="text-xs text-muted-foreground">{rows.length === 0 ? 'nothing injected yet' : `${rows.filter((r) => r.incident).length} of ${rows.length} seen`}</span>
        <ChevronDown className={cn('ml-auto size-4 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </button>
      {open && rows.length > 0 && (
        <table className="mt-2 w-full text-left text-xs" data-testid="injected-table">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="py-1 pr-3 font-medium">Injected</th>
              <th className="py-1 pr-3 font-medium">When</th>
              <th className="py-1 pr-3 font-medium">Seen as</th>
              <th className="py-1 font-medium">Delay</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.injected.key} className="border-t border-border/60 align-top" data-testid="injected-row" data-seen={r.incident ? 'yes' : 'no'}>
                <td className="py-1.5 pr-3 text-foreground">{r.injected.label}</td>
                <td className="py-1.5 pr-3 font-mono text-muted-foreground">
                  {formatT(r.injected.start)} → {r.injected.end === null ? 'ongoing' : formatT(r.injected.end)}
                </td>
                <td className="py-1.5 pr-3">
                  {r.incident ? (
                    <span>
                      {r.incident.path.filter((p) => p !== 'recovering' && p !== 'closed' && p !== 'open').join(' → ')}
                      <span className="font-mono text-muted-foreground"> · {formatT(r.incident.opened.payload.opened_at)}</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">not seen</span>
                  )}
                </td>
                <td className="py-1.5 font-mono text-muted-foreground">{r.delay === null ? '—' : `${formatDuration(r.delay)} later`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
