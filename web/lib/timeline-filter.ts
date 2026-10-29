// Filtros y buscador del timeline de eventos. Puro y con pruebas.
import type { Envelope } from './contracts'
import { groupOf, type Group } from './format.ts'

export type TimelineFilter = {
  hiddenGroups: ReadonlySet<Group>
  hiddenTypes: ReadonlySet<string>
  hiddenTopics: ReadonlySet<string>
  query: string
}

/** Topic de un evento sin el prefijo, el tipo y la versión: `air.d1`, `ai.monitor`, `sim.player`… */
export function topicOf(e: Envelope): string {
  const parts = e.topic.split('.')
  return parts.length === 7 ? `${parts[3]}.${parts[4]}` : e.topic
}

const haystacks = new WeakMap<Envelope, string>()

/** Texto donde busca el buscador: tipo, id, topic, fuente y contenido. Se calcula una vez. */
export function searchText(e: Envelope): string {
  let text = haystacks.get(e)
  if (text === undefined) {
    text = `${e.type} ${e.event_id} ${e.topic} ${e.source} ${JSON.stringify(e.payload)}`.toLowerCase()
    haystacks.set(e, text)
  }
  return text
}

export function matches(e: Envelope, f: TimelineFilter, terms: string[]): boolean {
  if (f.hiddenGroups.has(groupOf(e)) || f.hiddenTypes.has(e.type) || f.hiddenTopics.has(topicOf(e))) return false
  if (terms.length === 0) return true
  const text = searchText(e)
  return terms.every((t) => text.includes(t))
}

export const queryTerms = (query: string) => query.toLowerCase().split(/\s+/).filter(Boolean)

export function filterEvents(events: Envelope[], f: TimelineFilter): Envelope[] {
  const terms = queryTerms(f.query)
  return events.filter((e) => matches(e, f, terms))
}

/** Recuento por clave (tipo o topic), ordenado por clave. */
export function countBy(events: Envelope[], key: (e: Envelope) => string): [string, number][] {
  const counts = new Map<string, number>()
  for (const e of events) counts.set(key(e), (counts.get(key(e)) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))
}
