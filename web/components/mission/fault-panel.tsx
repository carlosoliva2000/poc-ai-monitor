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
 * plataforma rechazaría el `fault`). `mute` para cualquier fuente; `loss` solo para el GPS, que
 * admite las dos a la vez (receptor muerto); el resto de fuentes, un fallo como máximo.
 */
export function FaultPanel({ state, onControl }: Props) {
  const enabled = Boolean(state?.interactive) && state?.status !== 'finished' && Boolean(state?.scenario)
  const active = state?.active_faults ?? []
  const find = (source: SensorSource, mode: FaultMode) => active.find((f) => f.source === source && f.mode === mode)
  const gpsLoss = find('gps', 'loss')
  const deadReceiver = Boolean(gpsLoss && find('gps', 'mute'))

  const set = (source: SensorSource, mode: FaultMode, on: boolean) =>
    onControl({ action: 'fault', value: { source, mode, active: on } })

  return (
    <section aria-labelledby="fault-title" className="flex flex-col gap-2 border-t border-border bg-card px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="fault-title" className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <ZapOff className="size-4 text-muted-foreground" aria-hidden="true" />
          Inject fault
        </h2>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {SOURCES.map((source) => {
          const fault = find(source, 'mute')
          const muted = Boolean(fault)
          return (
            <button
              key={source}
              type="button"
              role="switch"
              aria-checked={muted}
              aria-label={`Mute ${SOURCE_LABEL[source]}`}
              disabled={!enabled || (muted && fault?.origin === 'scenario')}
              onClick={() => set(source, 'mute', !muted)}
              className={cn(
                'rounded-md border px-2.5 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45',
                muted ? 'border-destructive bg-destructive/10 text-destructive' : 'border-border bg-background text-foreground hover:bg-muted',
              )}
            >
              {muted ? 'Muted: ' : 'Mute '}
              {SOURCE_LABEL[source]}
            </button>
          )
        })}
        <button
          type="button"
          role="switch"
          aria-checked={Boolean(gpsLoss)}
          aria-label="GPS loss"
          disabled={!enabled || gpsLoss?.origin === 'scenario'}
          onClick={() => set('gps', 'loss', !gpsLoss)}
          className={cn(
            'rounded-md border px-2.5 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45',
            gpsLoss ? 'border-destructive bg-destructive/10 text-destructive' : 'border-border bg-background text-foreground hover:bg-muted',
          )}
        >
          {gpsLoss ? 'GPS loss in progress' : 'GPS loss'}
        </button>
      </div>

      <p className="text-xs text-muted-foreground" data-testid="active-faults">
        {active.length === 0
          ? 'No faults in progress.'
          : `In progress: ${active.map((f) => `${SOURCE_LABEL[f.source]} · ${f.mode === 'mute' ? 'muted' : 'loss'} (${f.origin === 'manual' ? 'manual' : 'scheduled'})`).join(' · ')}${deadReceiver ? ' — GPS receiver dead: dead reckoning and no output' : ''}`}
      </p>
    </section>
  )
}
