// Las dos vistas de la web: la del alumno (incidentes, evidencias, explicaciones) y la del
// instructor (además, lo inyectado y la verdad del ejercicio). Puro y con pruebas.
import type { Envelope } from './contracts'

export type View = 'student' | 'instructor'
export const VIEWS: { id: View; label: string }[] = [
  { id: 'student', label: 'Student' },
  { id: 'instructor', label: 'Instructor' },
]
export const DEFAULT_VIEW: View = 'instructor'
export const reviveView = (raw: unknown): View => (raw === 'student' ? 'student' : DEFAULT_VIEW)

/** Eventos que son del instructor: fallos, modo interactivo, comandos, lo programado en el ejercicio
 *  (`ExerciseInjects`, v1.4) y el debriefing (`DebriefGenerated`, v1.4: lleva la verdad). */
const INSTRUCTOR_ONLY_TYPES = new Set(['FaultInjected', 'FaultCleared', 'InteractiveModeChanged', 'InstructorCommand', 'ExerciseInjects', 'DebriefGenerated'])
const INSTRUCTOR_AGENTS = new Set(['chat-instructor', 'translator', 'debrief'])
const CONVERSATION_TYPES = new Set(['OperatorMessage', 'AgentReply', 'AgentReplyChunk'])
const AGENT_TYPES = new Set(['AgentActivity', 'AgentToolCall'])

/** Lo que la vista del alumno no enseña: eventos del simulador del instructor y su chat. */
export function isInstructorOnly(e: Envelope): boolean {
  if (INSTRUCTOR_ONLY_TYPES.has(e.type)) return true
  const p = e.payload as { conversation_id?: string; agent?: string }
  if (CONVERSATION_TYPES.has(e.type)) return p.conversation_id === 'instructor'
  if (AGENT_TYPES.has(e.type)) return INSTRUCTOR_AGENTS.has(p.agent ?? '')
  return false
}

export const eventsForView = (events: Envelope[], view: View): Envelope[] => (view === 'student' ? events.filter((e) => !isInstructorOnly(e)) : events)
