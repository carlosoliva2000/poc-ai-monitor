'use client'

import { useEffect, useMemo, useState } from 'react'
import { useStoredState } from '@/hooks/use-stored-state'
import { clampConsoleWidth, DEFAULT_CONSOLE } from '@/lib/map-view'
import { usePlatform, useTruth } from '@/hooks/use-platform'
import { derive } from '@/lib/derive'
import { AgentConsole } from './agent-console'
import { DroneMap } from './drone-map'
import { EventTimeline } from './event-timeline'
import { FaultPanel } from './fault-panel'
import { LayersPanel, useLayers } from './layers-panel'
import { MissionHeader } from './mission-header'
import { progressMarks, SimControls } from './sim-controls'
import { TelemetryStrip } from './telemetry-strip'

export function MissionConsole() {
  const { connection, events, state, errors, chunks, activity, toolCalls, reportPhase, scenarios, plan, live, setTruthFeed, control, sendOperatorMessage } = usePlatform()
  const [layers, setLayers] = useLayers()
  const data = useMemo(() => derive(events), [events])
  const truth = useTruth(layers.truth, state?.run_id ?? null, state?.status === 'running')
  // La posición real en directo solo se pide mientras su capa está activa.
  useEffect(() => setTruthFeed(layers.truthDrone), [layers.truthDrone, setTruthFeed])
  const [storedWidth, setStoredWidth] = useStoredState<number>('poc-console-width-v1', DEFAULT_CONSOLE, (raw) => (typeof raw === 'number' ? raw : DEFAULT_CONSOLE))
  const [viewport, setViewport] = useState(1440)
  useEffect(() => {
    const measure = () => setViewport(window.innerWidth)
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])
  const consoleWidth = clampConsoleWidth(storedWidth, viewport)
  const marks = useMemo(() => progressMarks(events), [events])

  const started = events.find((e) => e.type === 'SimulationStarted')
  const duration = started ? (started.payload as { duration_s: number }).duration_s : (plan?.duration_s ?? 0)

  const waitingAgent = state?.status === 'paused' && data.pauseReason === 'waiting_agent'
  const next = data.pending[0]
  let waiting: string | null = null
  if (waitingAgent) {
    if (next) {
      const id = (next.payload as { detection_id: string }).detection_id
      waiting = `Waiting for the monitor: analysing ${next.type === 'DetectionCleared' ? `the closure of ${id}` : id}…`
    } else {
      waiting = 'Waiting for the monitor…'
    }
  }
  const agentBusy = Object.keys(activity).length > 0

  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh lg:overflow-hidden">
      <MissionHeader missionId={plan?.mission_id ?? '—'} state={state} connection={connection} waiting={waitingAgent} agentBusy={agentBusy} />

      {errors.length > 0 && (
        <div className="flex flex-col gap-1 border-b border-destructive/30 bg-destructive/10 px-4 py-2" role="alert">
          {errors.map((e) => (
            <p key={e.id} className="text-sm text-destructive">
              {e.message}
            </p>
          ))}
        </div>
      )}
      {connection === 'closed' && (
        <p className="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive" role="alert">
          No connection to the platform (ws://127.0.0.1:8100/ws). Retrying…
        </p>
      )}

      <main
        className="grid flex-1 gap-px bg-border lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_var(--console-w)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden"
        style={{ '--console-w': `${consoleWidth}px` } as React.CSSProperties}
      >
        <div className="relative flex min-h-0 flex-col bg-card lg:h-full lg:overflow-y-auto lg:[container-type:size]">
          <section aria-labelledby="map-title" className="flex flex-col">
            <div className="flex flex-col gap-1.5 px-4 pb-2 pt-2.5">
              <h2 id="map-title" className="text-sm font-semibold text-foreground">
                Top view · x,y plane (m)
              </h2>
              <LayersPanel layers={layers} onChange={setLayers} />
            </div>
            <div className="aspect-[1060/652] w-full border-y border-border bg-card lg:aspect-auto lg:h-[clamp(420px,60dvh,900px)]">
              <DroneMap plan={plan} data={data} truth={truth} live={live} layers={layers} faults={state?.active_faults ?? []} running={state?.status === 'running'} speed={state?.speed ?? 1} simTime={state?.sim_time ?? 0} />
            </div>
          </section>

          <SimControls state={state} data={data} marks={marks} duration={duration} scenarios={scenarios} waiting={waiting} onControl={control} />
          <FaultPanel state={state} onControl={control} />
          <TelemetryStrip data={data} plan={plan} faults={state?.active_faults ?? []} />

          <div className="flex min-h-72 flex-1 border-t border-border lg:h-[100cqh] lg:min-h-0 lg:flex-none">
            <EventTimeline events={events} cursor={state?.cursor ?? 0} total={state?.total_events ?? 0} />
          </div>
        </div>

        <div className="relative min-h-[80dvh] bg-card lg:h-full lg:min-h-0 lg:overflow-hidden">
          <ResizeHandle width={consoleWidth} viewport={viewport} onChange={setStoredWidth} />
          <AgentConsole events={events} data={data} chunks={chunks} activity={activity} toolCalls={toolCalls} reportPhase={reportPhase} finished={state?.status === 'finished'} onSend={sendOperatorMessage} />
        </div>
      </main>
    </div>
  )
}

/** Asa vertical entre la columna izquierda y la consola del agente (solo en `lg`). Arrastrar o
 *  flechas con el foco; doble clic restablece. El ancho se recuerda en `localStorage`. */
function ResizeHandle({ width, viewport, onChange }: { width: number; viewport: number; onChange: (w: number) => void }) {
  const [drag, setDrag] = useState<{ x: number; width: number } | null>(null)
  const set = (w: number) => onChange(clampConsoleWidth(w, viewport))
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the agent console"
      aria-valuenow={width}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      data-testid="console-handle"
      className={`absolute inset-y-0 left-0 z-20 hidden w-1.5 cursor-col-resize touch-none transition-colors hover:bg-primary/30 focus-visible:bg-primary/40 focus-visible:outline-none lg:block ${drag ? 'bg-primary/40' : ''}`}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        setDrag({ x: e.clientX, width })
      }}
      onPointerMove={(e) => drag && set(drag.width + (drag.x - e.clientX))}
      onPointerUp={() => setDrag(null)}
      onPointerCancel={() => setDrag(null)}
      onDoubleClick={() => set(DEFAULT_CONSOLE)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') set(width + 24)
        else if (e.key === 'ArrowRight') set(width - 24)
        else return
        e.preventDefault()
      }}
    />
  )
}
