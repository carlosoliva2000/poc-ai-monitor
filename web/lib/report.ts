// El informe llega como un solo Markdown (`ReportGenerated`). Desde la Fase 14.1 termina con la
// autoevaluación del monitor, para quien evalúa el ejercicio: la web muestra el informe de misión
// y, plegada, esa autoevaluación. Los informes anteriores no tienen anexo.

export const ANNEX_TITLE = 'Annex: monitor self-assessment'

export type ReportParts = { mission: string; annex: string | null; annexTitle: string }

export function splitReport(markdown: string): ReportParts {
  const lines = markdown.split('\n')
  const start = lines.findIndex((line) => line.trim() === `## ${ANNEX_TITLE}`)
  if (start < 0) return { mission: markdown, annex: null, annexTitle: ANNEX_TITLE }
  const mission = lines.slice(0, start).join('\n').trimEnd()
  const annex = lines
    .slice(start + 1)
    .join('\n')
    .trim()
  return { mission, annex: annex || null, annexTitle: ANNEX_TITLE }
}
