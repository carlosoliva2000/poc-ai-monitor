import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ReactMarkdown from 'react-markdown'
import { CHAT_MARKDOWN_PROPS } from './chat-markdown.ts'

const render = (text: string) => renderToStaticMarkup(createElement(ReactMarkdown, { ...CHAT_MARKDOWN_PROPS, children: text }))

test('negrita, cursiva y código en línea', () => {
  const html = render('The last event is **bat-0002**, *silent* since `T+00:51`.')
  assert.match(html, /<strong>bat-0002<\/strong>/)
  assert.match(html, /<em>silent<\/em>/)
  assert.match(html, /<code>T\+00:51<\/code>/)
  assert.doesNotMatch(html, /\*\*/)
})

test('listas con viñetas y numeradas', () => {
  const html = render('- one\n- two\n\n1. first\n2. second')
  assert.match(html, /<ul>\s*<li>one<\/li>\s*<li>two<\/li>\s*<\/ul>/)
  assert.match(html, /<ol>\s*<li>first<\/li>\s*<li>second<\/li>\s*<\/ol>/)
})

test('bloque de código', () => {
  const html = render('```\nbat-0002 {battery_pct: 98.0}\n```')
  assert.match(html, /<pre><code>bat-0002 \{battery_pct: 98\.0\}\n<\/code><\/pre>/)
})

test('el HTML embebido sale como texto, nunca como elemento', () => {
  const html = render('<b>raw html</b> and <script>alert(1)</script> <img src=x onerror=alert(1)>')
  assert.doesNotMatch(html, /<b>|<script|<img/)
  assert.match(html, /&lt;b&gt;raw html&lt;\/b&gt;/)
})

test('títulos, enlaces y tablas pierden el formato pero conservan el texto', () => {
  const html = render('# Title\n\nSee [the link](http://example.com) | a | b |')
  assert.doesNotMatch(html, /<h1|<a |<table/)
  assert.match(html, /Title/)
  assert.match(html, /the link/)
})

test('texto sin Markdown no cambia', () => {
  assert.equal(render('Plain answer with T+03:42 and gps-000221.'), '<p>Plain answer with T+03:42 and gps-000221.</p>')
})
