// Limpieza de presentación de los textos del monitor. El evento, eval.md y el informe conservan
// el texto original; esto solo cambia lo que se pinta.

// Identificador de campo: `disagreed`, `with_drift`, `wind.mean_speed_mps`.
const IDENT = String.raw`[A-Za-z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)*`
const KEY = new RegExp(String.raw`(?<![\w.])(${IDENT})\s*([=:])`, 'g')
// Valor «simple»: hasta tres palabras (`true`, `4,9°`, `1.9 m/s`); si hay más, es prosa.
const SIMPLE_VALUE = /^[\w.,°%/+\-]+(?:\s[\w.,°%/+\-]+){0,2}$/
const GROUP = /(\s*)\(([^()]*)\)(\s*)/g

// Con «=» vale cualquier identificador (en prosa no se escribe «a=b»); con «:» se exige guion
// bajo o punto, para no confundir «(nota: algo)» con un campo.
function isFieldKey(ident: string, sep: string): boolean {
  return sep === '=' || /[._]/.test(ident)
}

// ¿El contenido de un paréntesis son solo expresiones campo=valor o campo: valor?
function onlyFieldValues(content: string): boolean {
  const keys = [...content.matchAll(KEY)].filter((m) => isFieldKey(m[1], m[2]))
  if (keys.length === 0 || content.slice(0, keys[0].index).trim() !== '') return false
  return keys.every((m, i) => {
    const start = m.index + m[0].length
    const end = i + 1 < keys.length ? keys[i + 1].index : content.length
    const value = content.slice(start, end).replace(/[\s,;]+$/, '').trim()
    return SIMPLE_VALUE.test(value)
  })
}

/** Quita los paréntesis que solo contienen expresiones campo=valor o campo: valor. */
export function stripFieldValues(text: string): string {
  return text.replace(GROUP, (whole, before: string, content: string, after: string, offset: number) => {
    if (!onlyFieldValues(content)) return whole
    // Al principio del texto no hay nada a lo que pegarse: se quita el espacio de después.
    if (offset === 0) return ''
    // Si lo que sigue es puntuación, el hueco de antes desaparece; si no, queda un solo espacio.
    return after === '' || /^[.,;:)]/.test(text.slice(offset + whole.length)) ? '' : ' '
  })
}
