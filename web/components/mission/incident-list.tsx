'use client'

import { useEffect, useMemo, useState } from 'react'
import type { Envelope } from '@/lib/contracts'
import { incidents, type IncidentView } from '@/lib/derive'
import { SEVERITY_LABEL } from '@/lib/format'
import { STATE_LABEL } from '@/lib/incidents'
import { cn } from '@/lib/utils'
import { IncidentCard } from './incident-card'
import { SEVERITY_CLASS } from './monitor-feed'

type Props = {
  events: Envelope[]
  /** Instante actual de la simulación. */
  simTime: number
}

/** Reloj de pared que avanza cada segundo: el «pending…» del texto del asistente caduca. */
function useNow(periodMs = 1000): number | undefined {
  const [now, setNow] = useState<number | undefined>(undefined)
  useEffect(() => {
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), periodMs)
    return () => window.clearInterval(timer)
  }, [periodMs])
  return now
}

/**
 * La lista de incidentes del monitor de situación (contrato v1.1): arriba los abiertos, los más
 * recientes primero, y debajo los cerrados, plegados. La cabecera resume cada incidente en una
 * línea con su recorrido («GPS spoofing · recovering → closed»).
 */
export function IncidentList({ events, simTime }: Props) {
  const now = useNow()
  const list = useMemo(() => incidents(events, now), [events, now])
  const open = list.filter((i) => i.open).reverse()
  const closed = list.filter((i) => !i.open).reverse()

  return (
    <div className="flex min-h-48 flex-[3] flex-col overflow-hidden" data-testid="incident-list">
      <Summary list={list} />
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3" role="log" aria-live="polite" aria-label="Incidents">
        {list.length === 0 && (
          <p className="m-auto max-w-64 text-center text-sm leading-relaxed text-muted-foreground text-pretty" data-testid="no-incidents">
            No incidents. The situation monitor opens one when the sensors show a problem with the flight.
          </p>
        )}
        {open.map((i) => (
          <IncidentCard key={i.id} incident={i} simTime={simTime} />
        ))}
        {closed.length > 0 && (
          <section aria-label="Closed incidents" className="flex flex-col gap-2" data-testid="closed-incidents">
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Closed ({closed.length})</h3>
            {closed.map((i) => (
              <IncidentCard key={i.id} incident={i} simTime={simTime} />
            ))}
          </section>
        )}
      </div>
    </div>
  )
}

function Summary({ list }: { list: IncidentView[] }) {
  if (list.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1.5 border-b border-border px-4 py-2 text-xs" aria-label="Incidents (one per incident)" data-testid="incident-summary">
      {list.map((i) => {
        const p = i.latest.payload
        return (
          <li key={i.id} className={cn('flex items-center gap-1.5 rounded-full border px-2 py-0.5', i.open ? 'border-destructive/50 bg-destructive/5' : 'border-border text-muted-foreground')} title={`${i.id} · ${i.path.join(' → ')}`} data-testid="incident-chip">
            <span>{p.name}</span>
            <span className={cn('rounded-sm px-1 text-[10px] font-medium', SEVERITY_CLASS[p.severity])}>{SEVERITY_LABEL[p.severity]}</span>
            <span>{STATE_LABEL[p.state]}</span>
          </li>
        )
      })}
    </ul>
  )
}
