'use client'

import { ZapOff } from 'lucide-react'
import { SOURCES, type ControlMessage, type FaultMode, type PlayerState, type SensorSource } from '@/lib/contracts'
import { SOURCE_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'

type Props = {
  state: PlayerState | null
  onControl: (message: ControlMessage) => void
}

/**
 * Inyectar fallo. Con el modo interactivo apagado los controles están deshabilitados (la
 * plataforma rechazaría el `fault`). `mute` para cualquier fuente; `loss` solo para el GPS.
 */
export function FaultPanel({ state, onControl }: Props) {
  const enabled = Boolean(state?.interactive) && state?.status !== 'finished' && Boolean(state?.scenario)
  const active = state?.active_faults ?? []
  const find = (source: SensorSource) => active.find((f) => f.source === source)

  const set = (source: SensorSource, mode: FaultMode, on: boolean) =>
    onControl({ action: 'fault', value: { source, mode, active: on } })

  return (
    <section aria-labelledby="fault-title" className="flex flex-col gap-2 border-t border-border bg-card px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="fault-title" className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <ZapOff className="size-4 text-muted-foreground" aria-hidden="true" />
          Inyectar fallo
        </h2>
        {!enabled && <span className="text-xs text-muted-foreground">Activa el «Modo interactivo» (y carga un escenario) para inyectar fallos.</span>}
        <span className="text-[11px] italic text-muted-foreground">el agente no ve estos eventos, solo sus efectos</span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {SOURCES.map((source) => {
          const fault = find(source)
          const muted = fault?.mode === 'mute'
          // El fallo de una fuente es único: si tiene `loss`, no se puede silenciar a la vez.
          const blocked = Boolean(fault) && !muted
          return (
            <button
              key={source}
              type="button"
              role="switch"
              aria-checked={muted}
              aria-label={`Silenciar ${SOURCE_LABEL[source]}`}
              disabled={!enabled || blocked || (muted && fault?.origin === 'scenario')}
              onClick={() => set(source, 'mute', !muted)}
              className={cn(
                'rounded-md border px-2.5 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45',
                muted ? 'border-destructive bg-destructive/10 text-destructive' : 'border-border bg-background text-foreground hover:bg-muted',
              )}
            >
              {muted ? 'Silenciado: ' : 'Silenciar '}
              {SOURCE_LABEL[source]}
            </button>
          )
        })}
        <button
          type="button"
          role="switch"
          aria-checked={find('gps')?.mode === 'loss'}
          aria-label="Pérdida de GPS"
          disabled={!enabled || (Boolean(find('gps')) && find('gps')?.mode !== 'loss') || (find('gps')?.mode === 'loss' && find('gps')?.origin === 'scenario')}
          onClick={() => set('gps', 'loss', find('gps')?.mode !== 'loss')}
          className={cn(
            'rounded-md border px-2.5 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45',
            find('gps')?.mode === 'loss' ? 'border-destructive bg-destructive/10 text-destructive' : 'border-border bg-background text-foreground hover:bg-muted',
          )}
        >
          {find('gps')?.mode === 'loss' ? 'Pérdida de GPS en curso' : 'Pérdida de GPS'}
        </button>
      </div>

      <p className="text-xs text-muted-foreground" data-testid="active-faults">
        {active.length === 0
          ? 'Sin fallos en curso.'
          : `En curso: ${active.map((f) => `${SOURCE_LABEL[f.source]} · ${f.mode === 'mute' ? 'silenciado' : 'pérdida'} (${f.origin === 'manual' ? 'manual' : 'programado'})`).join(' · ')}`}
      </p>
    </section>
  )
}
