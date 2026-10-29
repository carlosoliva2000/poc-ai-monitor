// Filtros y buscador del timeline de eventos. Puro y con pruebas.
import type { Envelope } from './contracts'
import { GROUPS, groupOf, type Group } from './format.ts'

/**
 * Filtro por tipo o por topic. `only: false`: se ven todos menos `keys`. `only: true`: se ven
 * **solo** `keys` (así «None» también oculta lo que aparezca después).
 */
export type KeyFilter = { only: boolean; keys: ReadonlySet<string> }
export const ALL_KEYS: KeyFilter = { only: false, keys: new Set() }
export const NO_KEYS: KeyFilter = { only: true, keys: new Set() }

export type TimelineFilter = {
  hiddenGroups: ReadonlySet<Group>
  types: KeyFilter
  topics: KeyFilter
  query: string
}

/** Fuentes ocultas por defecto: GPS y radar, muy verbosos. */
export const DEFAULT_HIDDEN_GROUPS: Group[] = ['gps', 'radar']
export const hideNoGroups = (): Group[] => []
export const hideAllGroups = (): Group[] => GROUPS.map((g) => g.id)

export const keyVisible = (f: KeyFilter, key: string) => (f.only ? f.keys.has(key) : !f.keys.has(key))

/** Marca o desmarca una clave, en cualquiera de los dos modos. */
export function toggleKey(f: { only: boolean; keys: string[] }, key: string): { only: boolean; keys: string[] } {
  return { only: f.only, keys: f.keys.includes(key) ? f.keys.filter((k) => k !== key) : [...f.keys, key] }
}

/** Cuántas de las claves conocidas se ven con este filtro. */
export const visibleKeyCount = (f: KeyFilter, known: string[]) => known.filter((k) => keyVisible(f, k)).length

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
  if (f.hiddenGroups.has(groupOf(e)) || !keyVisible(f.types, e.type) || !keyVisible(f.topics, topicOf(e))) return false
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
