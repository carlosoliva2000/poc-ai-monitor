// Las reglas de cada faceta tal como las ejecuta el monitor, en palabras para la ventana «Rules».
// Hay dos ficheros generados, uno por juego de tablas: las congeladas de la E7b
// (`situation-tables-frozen.json`, el valor por defecto, 13 tablas aprendidas y la regla de la
// situación) y las escritas a mano del vídeo (`situation-tables.json`, alternativa). El incidente dice
// cuál se ejecutó (`table`). Puro y con pruebas.
import { describeCell, describeOutput, describeSupport, facetLabel } from './incidents.ts'

/** Nombre (`IncidentUpdated.table`) del juego de tablas escrito a mano; cualquier otro es el congelado. */
export const HANDWRITTEN_TABLE = 'handwritten-video'

/** Elige el fichero de reglas que ejecutó el monitor. */
export function pickRules(table: string | undefined, frozen: RulesFile, handwritten: RulesFile): RulesFile {
  return table === HANDWRITTEN_TABLE ? handwritten : frozen
}

export type RuleRow = { id: string; note: string; when: Record<string, string>; then: Record<string, string> }
export type RuleTable = {
  table: string
  description: string
  hit_policy: string
  inputs: string[]
  outputs: string[]
  rules: RuleRow[]
}
export type RulesFile = { facets: Record<string, RuleTable> }

export type RuleLine = { id: string; note: string; conditions: string[]; output: string; support: string | null; matched: boolean }
export type RulesView = { title: string; description: string; policy: string; lines: RuleLine[] }

/** La tabla de una faceta lista para pintar, con la fila que encajó marcada. `null` si la faceta no tiene tabla. */
export function rulesView(file: RulesFile, facet: string, matchedRule: string | null): RulesView | null {
  const table = file.facets[facet]
  if (!table) return null
  return {
    title: facetLabel(facet),
    description: table.description,
    policy: table.hit_policy,
    lines: table.rules.map((rule) => ({
      id: rule.id,
      note: rule.note,
      conditions: Object.entries(rule.when).map(([feature, cell]) => describeCell(feature, cell)),
      output: describeOutput(rule.then),
      support: describeSupport(rule.then),
      matched: rule.id === matchedRule,
    })),
  }
}
