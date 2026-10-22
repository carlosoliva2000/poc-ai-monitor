'use client'

import { Hourglass, Pause, Play, RotateCcw, StepForward } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SPEEDS, type ControlMessage, type Envelope, type PlayerState, type ScenarioInfo } from '@/lib/contracts'
import type { Derived } from '@/lib/derive'
import { formatT } from '@/lib/format'
import { cn } from '@/lib/utils'

type Mark = { key: string; t: number; className: string; title: string }

const MARKS: Record<string, { className: string; label: string }> = {
  DetectionRaised: { className: 'bg-accent', label: 'detección' },
  AnomalyDetected: { className: 'bg-destructive', label: 'alerta' },
  AlertClosed: { className: 'bg-primary', label: 'cierre' },
  FaultInjected: { className: 'bg-foreground', label: 'fallo' },
  FaultCleared: { className: 'bg-muted-foreground', label: 'fin del fallo' },
  InteractiveModeChanged: { className: 'bg-muted-foreground', label: 'modo interactivo' },
}

export function progressMarks(events: Envelope[]): Mark[] {
  const out: Mark[] = []
  for (const e of events) {
    const m = MARKS[e.type]
    if (m) out.push({ key: e.event_id, t: e.sim_time, className: m.className, title: `${formatT(e.sim_time)} ${m.label}` })
  }
  return out
}

type Props = {
  state: PlayerState | null
  data: Derived
  marks: Mark[]
  duration: number
  scenarios: ScenarioInfo[]
  /** Aviso mientras el reproductor espera al monitor. */
  waiting: string | null
  onControl: (message: ControlMessage) => void
}

export function SimControls({ state, data, marks, duration, scenarios, waiting, onControl }: Props) {
  const status = state?.status ?? 'idle'
  const running = status === 'running'
  const finished = status === 'finished'
  const simTime = state?.sim_time ?? 0
  const pct = duration > 0 ? Math.min(100, (simTime / duration) * 100) : 0
  const loaded = Boolean(state?.scenario)
  const waitingAgent = status === 'paused' && data.pauseReason === 'waiting_agent'

  return (
    <div className="flex flex-col gap-3 border-t border-border bg-card px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="w-16 shrink-0 font-mono text-sm tabular-nums text-foreground">{formatT(simTime)}</span>
        <div
          className="relative h-2 flex-1 rounded-full bg-muted"
          role="progressbar"
          aria-label="Progreso de la simulación"
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(simTime)}
        >
          <div className="absolute inset-y-0 left-0 rounded-full bg-primary/30" style={{ width: `${pct}%` }} />
          {duration > 0 &&
            marks.map((m) => (
              <span
                key={m.key}
                title={m.title}
                className={cn('absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card', m.className)}
                style={{ left: `${Math.min(100, (m.t / duration) * 100)}%` }}
              />
            ))}
        </div>
        <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums text-muted-foreground">{formatT(duration)}</span>
      </div>

      {waitingAgent && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-md border border-accent/50 bg-accent/10 px-3 py-2 text-sm text-foreground"
          data-testid="waiting-agent"
        >
          <Hourglass className="size-4 shrink-0 animate-pulse text-accent" aria-hidden="true" />
          <span>{waiting ?? 'Esperando al monitor…'}</span>
          <span className="ml-auto text-xs text-muted-foreground">pausa automática, no es una pausa del usuario</span>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Escenario
            <select
              value={state?.scenario ?? ''}
              onChange={(e) => e.target.value && onControl({ action: 'load', value: e.target.value })}
              className="h-9 rounded-md border border-border bg-background px-2 font-sans text-sm normal-case tracking-normal text-foreground"
              aria-label="Escenario"
            >
              {!state?.scenario && <option value="">Elige un escenario…</option>}
              {scenarios.map((s) => (
                <option key={s.name} value={s.name} title={s.description}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {running ? (
            <Button onClick={() => onControl({ action: 'pause' })} size="lg" className="min-w-28">
              <Pause aria-hidden="true" />
              Pausar
            </Button>
          ) : (
            <Button onClick={() => onControl({ action: 'play' })} size="lg" className="min-w-28" disabled={!loaded || finished}>
              <Play aria-hidden="true" />
              {status === 'idle' ? 'Iniciar' : finished ? 'Terminada' : 'Reanudar'}
            </Button>
          )}
          <Button variant="outline" size="lg" onClick={() => onControl({ action: 'step' })} disabled={!loaded || finished}>
            <StepForward aria-hidden="true" />
            Paso
          </Button>
          <Button variant="outline" size="lg" onClick={() => onControl({ action: 'reset' })} disabled={!loaded}>
            <RotateCcw aria-hidden="true" />
            Reiniciar
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Toggle
            label="Esperar al agente"
            checked={state?.wait_agent ?? false}
            onChange={(v) => onControl({ action: 'wait_agent', value: v })}
          />
          <Toggle
            label="Modo interactivo"
            checked={state?.interactive ?? false}
            onChange={(v) => onControl({ action: 'interactive', value: v })}
          />
          <div className="flex items-center gap-2" role="group" aria-label="Velocidad de simulación">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Velocidad</span>
            <div className="flex rounded-md border border-border bg-background p-0.5">
              {SPEEDS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => onControl({ action: 'speed', value: option })}
                  aria-pressed={state?.speed === option}
                  className={cn(
                    'rounded-sm px-2 py-1 font-mono text-sm tabular-nums transition-colors',
                    state?.speed === option ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {option}×
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn('relative h-5 w-9 rounded-full border transition-colors', checked ? 'border-primary bg-primary' : 'border-border bg-muted')}
      >
        <span className={cn('absolute top-0.5 size-3.5 rounded-full bg-card shadow transition-all', checked ? 'left-[1.1rem]' : 'left-0.5')} />
      </button>
      {label}
    </label>
  )
}
