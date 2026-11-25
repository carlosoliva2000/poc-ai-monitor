// Las reglas de cada faceta tal como las ejecuta el monitor (`web/lib/situation-tables.json`, generado
// desde su `tables.yaml`), en palabras para la ventana «Rules». Puro y con pruebas.
import { describeCell, describeOutput, facetLabel } from './incidents.ts'

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

export type RuleLine = { id: string; note: string; conditions: string[]; output: string; matched: boolean }
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
      matched: rule.id === matchedRule,
    })),
  }
}
