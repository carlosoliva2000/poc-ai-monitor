/**
 * Markdown básico de las respuestas de los chats: negrita, cursiva, listas, código en línea y en
 * bloque. Todo lo demás (títulos, enlaces, tablas, imágenes) se queda como texto sin su formato y
 * el HTML embebido se escribe tal cual: `react-markdown` no interpreta HTML si no se le añade
 * `rehype-raw`, que aquí no se usa (https://github.com/remarkjs/react-markdown#security).
 */
export const CHAT_MARKDOWN_ELEMENTS = ['p', 'strong', 'em', 'ul', 'ol', 'li', 'code', 'pre'] as const

export const CHAT_MARKDOWN_PROPS = {
  allowedElements: [...CHAT_MARKDOWN_ELEMENTS],
  unwrapDisallowed: true,
}
