'use client'

import { useMemo } from 'react'
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
  const { connection, events, state, errors, chunks, activity, toolCalls, reportPhase, scenarios, plan, control, sendOperatorMessage } = usePlatform()
  const [layers, setLayers] = useLayers()
  const data = useMemo(() => derive(events), [events])
  const truth = useTruth(layers.truth, state?.run_id ?? null, state?.status === 'running')
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

      <main className="grid flex-1 gap-px bg-border lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(380px,460px)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden">
        <div className="relative flex min-h-0 flex-col bg-card lg:h-full lg:overflow-y-auto">
          <section aria-labelledby="map-title" className="flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2.5">
              <h2 id="map-title" className="text-sm font-semibold text-foreground">
                Top view · x,y plane (m)
              </h2>
              <LayersPanel layers={layers} onChange={setLayers} />
            </div>
            <div className="aspect-[1060/652] w-full bg-background px-2 lg:aspect-auto lg:h-[min(46dvh,500px)]">
              <DroneMap plan={plan} data={data} truth={truth} layers={layers} faults={state?.active_faults ?? []} running={state?.status === 'running'} speed={state?.speed ?? 1} simTime={state?.sim_time ?? 0} />
            </div>
          </section>

          <SimControls state={state} data={data} marks={marks} duration={duration} scenarios={scenarios} waiting={waiting} onControl={control} />
          <FaultPanel state={state} onControl={control} />
          <TelemetryStrip data={data} plan={plan} faults={state?.active_faults ?? []} />

          <div className="flex min-h-72 flex-1 border-t border-border lg:min-h-0">
            <EventTimeline events={events} cursor={state?.cursor ?? 0} total={state?.total_events ?? 0} />
          </div>
        </div>

        <div className="relative min-h-[80dvh] bg-card lg:h-full lg:min-h-0 lg:overflow-hidden">
          <AgentConsole events={events} data={data} chunks={chunks} activity={activity} toolCalls={toolCalls} reportPhase={reportPhase} finished={state?.status === 'finished'} onSend={sendOperatorMessage} />
        </div>
      </main>
    </div>
  )
}
