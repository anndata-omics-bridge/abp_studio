import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../../viewer/package.json', import.meta.url))
const { transformSync } = require('esbuild')

// The controller tests replace browser renderers with small DOM test doubles.
// Transpile the real TypeScript before evaluating it in that isolated context.
export function compiledSource (path) {
  return transformSync(readFileSync(path, 'utf8'), {
    loader: 'ts',
    format: 'esm',
    target: 'es2022',
    tsconfigRaw: { compilerOptions: { useDefineForClassFields: false } }
  }).code
}

export function isolatedSource (path) {
  return compiledSource(path)
    .replace(/import\s+[\s\S]*?from\s+['"][^'"]+['"];?\s*/g, '')
    .replace(/import\s+['"][^'"]+['"];?\s*/g, '')
    .replace(/export\s*\{[\s\S]*?\};?\s*/g, '')
    .replace(/export /g, '')
}
