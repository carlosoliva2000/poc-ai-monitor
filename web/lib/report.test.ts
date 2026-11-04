import assert from 'node:assert/strict'
import { test } from 'node:test'
import { splitReport } from './report.ts'

const WITH_ANNEX = `# Mission report

## Summary

The drone flew.

## Recommendations

1. Check the wind.

## Annex: monitor self-assessment

**Monitor figures** x.

### Assessment

- **Support:** it held.
`

test('separa el anexo del informe de misión', () => {
  const parts = splitReport(WITH_ANNEX)
  assert.ok(parts.mission.endsWith('1. Check the wind.'))
  assert.ok(!parts.mission.includes('Annex'))
  assert.ok(parts.annex?.startsWith('**Monitor figures** x.'))
  assert.ok(parts.annex?.includes('### Assessment'))
})

test('un informe sin anexo se muestra entero', () => {
  const old = '# Mission report\n\n## Monitor assessment\n\nOld layout.\n'
  const parts = splitReport(old)
  assert.equal(parts.mission, old)
  assert.equal(parts.annex, null)
})

test('un anexo vacío no se muestra', () => {
  assert.equal(splitReport('# R\n\n## Annex: monitor self-assessment\n\n').annex, null)
})
