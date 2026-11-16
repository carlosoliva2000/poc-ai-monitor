'use client'

import { ChevronDown, Wind } from 'lucide-react'
import { useMemo } from 'react'
import { useStoredState } from '@/hooks/use-stored-state'
import type { ControlMessage, Envelope, PlayerState } from '@/lib/contracts'
import { formatT } from '@/lib/format'
import { activeWind, COMPASS, compassDegrees, describeWind, exactPoint, LIMITS, parseForm, remaining, type WindForm } from '@/lib/instructor'
import { cn } from '@/lib/utils'

type Props = {
  state: PlayerState | null
  events: Envelope[]
  form: WindForm
  onForm: (form: WindForm) => void
  /** Abierto desde fuera (p. ej. «Edit» de una propuesta del chat). */
  forceOpen?: number
  onControl: (message: ControlMessage) => void
}

const input = 'w-20 rounded-md border border-border bg-background px-2 py-1 text-sm tabular-nums disabled:cursor-not-allowed disabled:opacity-45'

/**
 * Panel «Instructor» (desplegable, junto al de fallos): pone viento en directo. Como los fallos,
 * solo con el modo interactivo encendido. El viento es del instructor: el monitor lo descubre por
 * sus efectos, no se le avisa.
 */
export function InstructorPanel({ state, events, form, onForm, forceOpen = 0, onControl }: Props) {
  const [stored, setOpen] = useStoredState<boolean>('poc-instructor-open-v1', false, (raw) => raw === true)
  const open = stored || forceOpen > 0
  const enabled = Boolean(state?.interactive) && state?.status !== 'finished' && Boolean(state?.scenario)
  const simTime = state?.sim_time ?? 0
  const active = useMemo(() => activeWind(events, simTime), [events, simTime])
  const parsed = parseForm(form)
  const set = (patch: Partial<WindForm>) => onForm({ ...form, ...patch })
  const deg = Number(form.from_deg)
  const point = Number.isFinite(deg) ? exactPoint(deg) : null
  const left = active ? remaining(active, simTime) : null

  return (
    <section aria-labelledby="instructor-title" className="flex flex-col gap-2 border-t border-border bg-card px-4 py-2.5" data-testid="instructor-panel">
      <button type="button" aria-expanded={open} aria-controls="instructor-body" onClick={() => setOpen(!open)} className="flex items-center justify-between gap-2 text-left">
        <h2 id="instructor-title" className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Wind className="size-4 text-muted-foreground" aria-hidden="true" />
          Instructor
          {active && <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs font-normal text-foreground">wind on</span>}
        </h2>
        <ChevronDown className={cn('size-4 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </button>

      {open && (
        <div id="instructor-body" className="flex flex-col gap-2.5">
          <div role="radiogroup" aria-label="Wind direction (where it blows from)" className="grid grid-cols-8 gap-1 sm:grid-cols-16">
            {COMPASS.map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={point === p}
                disabled={!enabled}
                onClick={() => set({ from_deg: String(compassDegrees(p)) })}
                className={cn('rounded-md border px-1 py-0.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-45', point === p ? 'border-primary bg-primary/10 text-primary' : 'border-border bg-background hover:bg-muted')}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">From (°)</span>
              <input aria-label="Direction in degrees" type="number" min={0} max={360} step={1} value={form.from_deg} disabled={!enabled} onChange={(e) => set({ from_deg: e.target.value })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">Speed (m/s)</span>
              <input aria-label="Speed in m/s" type="number" min={0} max={LIMITS.speed} step={0.5} value={form.speed_mps} disabled={!enabled} onChange={(e) => set({ speed_mps: e.target.value })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">Gust (m/s)</span>
              <input aria-label="Gust in m/s" type="number" min={0} max={LIMITS.gust} step={0.5} value={form.gust_mps} disabled={!enabled} onChange={(e) => set({ gust_mps: e.target.value })} className={input} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">Duration (s)</span>
              <input aria-label="Duration in seconds" type="number" min={1} max={LIMITS.duration} step={5} value={form.duration_s} disabled={!enabled || form.untilCancelled} onChange={(e) => set({ duration_s: e.target.value })} className={input} />
            </label>
            <label className="flex items-center gap-1.5 pb-1.5 text-xs text-muted-foreground">
              <input type="checkbox" checked={form.untilCancelled} disabled={!enabled} onChange={(e) => set({ untilCancelled: e.target.checked })} />
              Until cancelled
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-xs text-muted-foreground">Ramp (s)</span>
              <input aria-label="Ramp in seconds" type="number" min={1} max={LIMITS.ramp} step={1} value={form.ramp_s} disabled={!enabled} onChange={(e) => set({ ramp_s: e.target.value })} className={input} />
            </label>
          </div>

          <p className="text-xs text-muted-foreground">
            Speed and direction push the drone. The ramp smooths the rise and the fall. The gust does not push the drone: only the weather station measures it, and it makes the wind notable.
          </p>
          {!parsed.ok && <p className="text-xs text-destructive" role="status">{parsed.errors.join(' · ')}</p>}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!enabled || !parsed.ok}
              onClick={() => parsed.ok && onControl({ action: 'instructor', value: { command: 'set_wind', params: parsed.params, issued_by: 'panel', text: null } })}
              className="rounded-md border border-primary bg-primary px-3 py-1 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              Apply
            </button>
            <button
              type="button"
              disabled={!enabled || !active}
              onClick={() => onControl({ action: 'instructor', value: { command: 'cancel_wind', params: null, issued_by: 'panel', text: null } })}
              className="rounded-md border border-border bg-background px-3 py-1 text-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-45"
            >
              Cancel wind
            </button>
            {!enabled && <span className="text-xs text-muted-foreground">Turn on interactive mode to send commands.</span>}
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground" data-testid="instructor-wind">
        {active
          ? `Instructor wind: ${describeWind(active.params).replace(/^Wind /, '')} · since ${formatT(active.since)} · ${left === null ? 'until cancelled' : `${Math.ceil(left)} s left`}`
          : 'No instructor wind.'}
      </p>
    </section>
  )
}
