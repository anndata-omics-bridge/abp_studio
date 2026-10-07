import assert from 'node:assert/strict'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { compiledSource } from './source.mjs'

const SOURCE = fileURLToPath(new URL('../../viewer/src/', import.meta.url))
const PROJECT = fileURLToPath(new URL('../../', import.meta.url))

function modules (directory = SOURCE) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) return modules(path)
    return entry.name.endsWith('.ts') && !entry.name.endsWith('.d.ts') ? [path] : []
  })
}

function importsOf (path) {
  return [...readFileSync(path, 'utf8').matchAll(/(?:import|export)\s+(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"]/g)]
    .map(match => match[1])
}

const local = path => relative(SOURCE, path).replaceAll('\\', '/')

test('TypeScript compilation preserves custom-element registration imports', () => {
  for (const viewer of ['corpus', 'fixture']) {
    const source = compiledSource(resolve(SOURCE, `${viewer}/app.ts`))
    assert.match(source, new RegExp(`import\\s+['"]\\./shell/${viewer}-app\\.js['"]`))
  }
})

test('both viewers have acyclic dependencies and independent composition roots', () => {
  const graph = new Map()
  for (const path of modules()) {
    const source = local(path)
    const viewer = source.split('/')[0]
    const targets = importsOf(path).filter(specifier => specifier.startsWith('.') && specifier.endsWith('.js'))
      .map(specifier => resolve(dirname(path), specifier.replace(/\.js$/, '.ts')))
    graph.set(path, targets)
    for (const targetPath of targets) {
      const target = local(targetPath)
      assert.ok(existsSync(targetPath), `${source} imports missing ${target}`)
      assert.ok(target.startsWith(`${viewer}/`) || target.startsWith('shared/'), `${source} crosses into ${target}`)
      assert.ok(!target.endsWith('/app.ts'), `${source} imports a composition root`)
      if (source.includes('/shell/')) {
        assert.ok(target.startsWith('shared/') || target.endsWith('/types.ts') || target === 'corpus/filters.ts', `${source} shell depends on ${target}`)
      }
    }
  }
  function visit (path, ancestors = new Set()) {
    assert.ok(!ancestors.has(path), `Import cycle at ${local(path)}`)
    const next = new Set([...ancestors, path])
    for (const target of graph.get(path) ?? []) visit(target, next)
  }
  for (const path of graph.keys()) visit(path)
})

test('viewer libraries are bundled locally with locked exact dependency versions', () => {
  const manifest = JSON.parse(readFileSync(resolve(PROJECT, 'viewer/package.json'), 'utf8'))
  const lock = JSON.parse(readFileSync(resolve(PROJECT, 'viewer/package-lock.json'), 'utf8'))
  for (const [name, version] of Object.entries(manifest.dependencies)) {
    assert.match(version, /^\d+\.\d+\.\d+$/)
    assert.equal(lock.packages[`node_modules/${name}`].version, version)
  }
  for (const path of modules()) {
    const source = readFileSync(path, 'utf8')
    assert.doesNotMatch(source, /(?:from|import)\s*['"]https?:/, `${local(path)} imports from the network`)
    assert.doesNotMatch(source, /@ts-(?:ignore|nocheck)|\bas any\b/, `${local(path)} suppresses type checking`)
    for (const specifier of importsOf(path).filter(specifier => !specifier.startsWith('.'))) {
      assert.ok(local(path).startsWith('shared/'), `${local(path)} bypasses a shared library adapter: ${specifier}`)
    }
  }
})

test('packaged viewers reference existing content-hashed local scripts and styles', () => {
  for (const viewer of ['corpus', 'fixture']) {
    const root = resolve(PROJECT, `src/apb_studio/${viewer}_viewer/web`)
    const index = readFileSync(resolve(root, 'index.html'), 'utf8')
    const assets = [...index.matchAll(/(?:href|src)=['"](\.\/assets\/[^'"]+)['"]/g)].map(match => match[1])
    assert.ok(assets.some(asset => asset.endsWith('.js')))
    assert.ok(assets.some(asset => asset.endsWith('.css')))
    assert.doesNotMatch(index, /https?:\/\//)
    for (const asset of assets) {
      assert.match(asset, /-[\w-]+\.(js|css)$/)
      assert.ok(existsSync(resolve(root, asset)), `${viewer} is missing ${asset}`)
    }
  }
})
