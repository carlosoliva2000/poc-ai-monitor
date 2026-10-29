'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  PLATFORM_HTTP,
  PLATFORM_WS,
  type AgentActivity,
  type AgentReplyChunk,
  type AgentToolCall,
  type Conversation,
  type ControlMessage,
  type Envelope,
  type EventDraft,
  type PlanFile,
  type PlayerState,
  type ScenarioInfo,
  type ServerMessage,
  type TruthFile,
  type TruthMessage,
} from '@/lib/contracts'

export type Connection = 'connecting' | 'open' | 'closed'
export type PlatformError = { id: number; message: string }
/** Estado del agente de informe según su `AgentActivity` (el informe en sí lo da `ReportGenerated`). */
export type ReportPhase = 'none' | 'writing' | 'finished'

const MAX_TOOL_CALLS = 800

const FLUSH_MS = 100
const RECONNECT_MS = 1000

/**
 * Cliente de la plataforma: WebSocket (`hello` como `web`, suscripción a todos los eventos) más la
 * API HTTP para lo que no es un evento (escenarios, ruta planificada y, si se pide, la verdad).
 * Los eventos llegan en ráfagas (a 16× son decenas por segundo): se acumulan en una referencia y
 * se vuelcan al estado de React cada 100 ms.
 */
export function usePlatform() {
  const [connection, setConnection] = useState<Connection>('connecting')
  const [events, setEvents] = useState<Envelope[]>([])
  const [state, setState] = useState<PlayerState | null>(null)
  const [errors, setErrors] = useState<PlatformError[]>([])
  const [chunks, setChunks] = useState<Record<string, string>>({})
  const [activity, setActivity] = useState<Record<string, AgentActivity>>({})
  const [toolCalls, setToolCalls] = useState<Envelope<AgentToolCall>[]>([])
  const [reportPhase, setReportPhase] = useState<ReportPhase>('none')
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([])
  const [plan, setPlan] = useState<PlanFile | null>(null)
  const [liveTruth, setLiveTruth] = useState<TruthMessage | null>(null)

  const ws = useRef<WebSocket | null>(null)
  const eventsRef = useRef<Envelope[]>([])
  const seen = useRef<Set<string>>(new Set())
  const chunksRef = useRef<Record<string, string>>({})
  const activityRef = useRef<Record<string, AgentActivity>>({})
  const toolCallsRef = useRef<Envelope<AgentToolCall>[]>([])
  const reportPhaseRef = useRef<ReportPhase>('none')
  const stateRef = useRef<PlayerState | null>(null)
  const wantTruth = useRef(false)
  const dirty = useRef(false)
  const errorId = useRef(0)

  const clearRun = useCallback(() => {
    eventsRef.current = []
    seen.current = new Set()
    chunksRef.current = {}
    activityRef.current = {}
    toolCallsRef.current = []
    reportPhaseRef.current = 'none'
    dirty.current = true
  }, [])

  const addEvent = useCallback(
    (event: Envelope, fromBackfill = false) => {
      // Al recuperar el timeline no se vacía nada: ya es el de la ejecución en curso.
      if (!fromBackfill && (event.type === 'SimulationStarted' || event.type === 'SimulationReset')) clearRun()
      if (event.ephemeral) {
        if (event.type === 'AgentReplyChunk') {
          const p = event.payload as unknown as AgentReplyChunk
          chunksRef.current = { ...chunksRef.current, [p.reply_to]: (chunksRef.current[p.reply_to] ?? '') + p.delta }
        } else if (event.type === 'AgentActivity') {
          const p = event.payload as unknown as AgentActivity
          const next = { ...activityRef.current }
          if (p.state === 'started') next[p.agent] = p
          else delete next[p.agent]
          activityRef.current = next
          if (p.agent === 'report') reportPhaseRef.current = p.state === 'started' ? 'writing' : 'finished'
        } else if (event.type === 'AgentToolCall' && !seen.current.has(event.event_id)) {
          seen.current.add(event.event_id)
          toolCallsRef.current = [...toolCallsRef.current, event as unknown as Envelope<AgentToolCall>].slice(-MAX_TOOL_CALLS)
        }
        dirty.current = true
        return
      }
      if (seen.current.has(event.event_id)) return
      seen.current.add(event.event_id)
      eventsRef.current.push(event)
      if (event.type === 'AgentReply') {
        const reply = event.payload as { reply_to: string }
        const { [reply.reply_to]: _done, ...rest } = chunksRef.current
        chunksRef.current = rest
      }
      dirty.current = true
    },
    [clearRun],
  )

  const showError = useCallback((message: string) => {
    const id = ++errorId.current
    setErrors((prev) => [...prev.slice(-2), { id, message }])
    window.setTimeout(() => setErrors((prev) => prev.filter((e) => e.id !== id)), 8000)
  }, [])

  // Volcado periódico de lo acumulado al estado de React.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!dirty.current) return
      dirty.current = false
      setEvents([...eventsRef.current].sort((a, b) => a.seq - b.seq))
      setChunks(chunksRef.current)
      setActivity(activityRef.current)
      setToolCalls(toolCallsRef.current)
      setReportPhase(reportPhaseRef.current)
    }, FLUSH_MS)
    return () => window.clearInterval(timer)
  }, [])

  // Conexión con reconexión simple. Tras reconectar se recupera el timeline (la web puede
  // abrirse a mitad de una ejecución).
  useEffect(() => {
    let closed = false
    let retry: number | undefined

    const backfill = async () => {
      try {
        const res = await fetch(`${PLATFORM_HTTP}/timeline`)
        const body = (await res.json()) as { events: Envelope[] }
        for (const event of body.events) addEvent(event, true)
      } catch {
        /* sin timeline: se sigue con lo que llegue por el socket */
      }
    }

    const connect = () => {
      setConnection('connecting')
      const socket = new WebSocket(PLATFORM_WS)
      ws.current = socket
      socket.onopen = () => {
        socket.send(JSON.stringify({ op: 'hello', client: 'web' }))
        socket.send(JSON.stringify({ op: 'subscribe', patterns: ['citadel.pub.evt.>'] }))
        if (wantTruth.current) socket.send(JSON.stringify({ op: 'truth_feed', active: true }))
        setConnection('open')
        void backfill()
      }
      socket.onmessage = (msg) => {
        const data = JSON.parse(msg.data as string) as ServerMessage
        if (data.op === 'event') addEvent(data.event)
        else if (data.op === 'state') {
          stateRef.current = data
          setState(data)
        } else if (data.op === 'truth') setLiveTruth(data)
        else if (data.op === 'error') showError(data.message)
      }
      socket.onclose = () => {
        setConnection('closed')
        if (!closed) retry = window.setTimeout(connect, RECONNECT_MS)
      }
      socket.onerror = () => socket.close()
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(retry)
      ws.current?.close()
    }
  }, [addEvent, showError])

  // Escenarios disponibles.
  useEffect(() => {
    if (connection !== 'open') return
    fetch(`${PLATFORM_HTTP}/scenarios`)
      .then((r) => r.json())
      .then((b: { scenarios: ScenarioInfo[] }) => setScenarios(b.scenarios))
      .catch(() => setScenarios([]))
  }, [connection])

  // Ruta planificada: se pide al cargar un escenario nuevo (cambia el `run_id`).
  const runId = state?.run_id ?? null
  useEffect(() => {
    if (!runId) {
      setPlan(null)
      return
    }
    fetch(`${PLATFORM_HTTP}/plan`)
      .then((r) => (r.ok ? r.json() : null))
      .then((p: PlanFile | null) => setPlan(p))
      .catch(() => setPlan(null))
  }, [runId])

  const control = useCallback((message: ControlMessage) => {
    const socket = ws.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    socket.send(JSON.stringify({ op: 'control', ...message }))
  }, [])

  /** Pide o deja de pedir la posición real en directo (mensaje `truth` del WebSocket, fuera del bus). */
  const setTruthFeed = useCallback((active: boolean) => {
    wantTruth.current = active
    if (!active) setLiveTruth(null)
    const socket = ws.current
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ op: 'truth_feed', active }))
  }, [])

  /** Publica un `OperatorMessage`. El id `ops-NNNN` lo calcula la web (máximo visto + 1): con dos
   *  pestañas abiertas pueden repetirse y la plataforma rechazaría el mensaje. */
  const sendOperatorMessage = useCallback((conversation: Conversation, text: string): boolean => {
    const socket = ws.current
    const current = stateRef.current
    const last = eventsRef.current.reduce<Envelope | null>((a, e) => (a === null || e.seq > a.seq ? e : a), null)
    if (!socket || socket.readyState !== WebSocket.OPEN || !current || !last) {
      showError('The message was not sent: no connection to the platform or no scenario loaded.')
      return false
    }
    let max = 0
    for (const e of eventsRef.current) {
      if (e.event_id.startsWith('ops-')) max = Math.max(max, Number(e.event_id.slice(4)) || 0)
    }
    const t0 = Date.parse(last.event_time) - last.sim_time * 1000
    const simTime = Math.max(current.sim_time, last.sim_time)
    const event: EventDraft = {
      event_id: `ops-${String(max + 1).padStart(4, '0')}`,
      topic: `citadel.pub.evt.ops.${conversation}.OperatorMessage.v1`,
      type: 'OperatorMessage',
      source: 'web-operator',
      asset: null,
      sim_time: simTime,
      event_time: new Date(t0 + simTime * 1000).toISOString().replace(/\.000Z$/, 'Z'),
      causation_id: null,
      ephemeral: false,
      payload: { conversation_id: conversation, text },
    }
    socket.send(JSON.stringify({ op: 'publish', event }))
    return true
  }, [showError])

  return { connection, events, state, errors, chunks, activity, toolCalls, reportPhase, scenarios, plan, liveTruth, setTruthFeed, control, sendOperatorMessage }
}

/** La verdad de la simulación en curso (`GET /api/truth`). Solo se consulta con la capa activa. */
export function useTruth(enabled: boolean, runId: string | null, running: boolean) {
  const [truth, setTruth] = useState<TruthFile | null>(null)
  useEffect(() => {
    if (!enabled || !runId) {
      setTruth(null)
      return
    }
    let cancelled = false
    const load = () =>
      fetch(`${PLATFORM_HTTP}/truth`)
        .then((r) => (r.ok ? r.json() : null))
        .then((t: TruthFile | null) => {
          if (!cancelled) setTruth(t)
        })
        .catch(() => {})
    void load()
    if (!running) return () => void (cancelled = true)
    const timer = window.setInterval(load, 500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [enabled, runId, running])
  return truth
}
