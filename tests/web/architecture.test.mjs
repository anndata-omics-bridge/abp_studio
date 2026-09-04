import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const WEB_ROOT = fileURLToPath(new URL('../../src/apb_studio/fixture_viewer/web/', import.meta.url))

/** @returns {string[]} Every production JavaScript module. */
function modules (directory = WEB_ROOT) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) return modules(path)
    return entry.name.endsWith('.js') ? [path] : []
  })
}

/**
 * Extract static relative imports without executing CDN-backed modules in Node.
 *
 * @param {string} path Module path.
 * @returns {string[]} Imported specifiers.
 */
function importsOf (path) {
  const source = readFileSync(path, 'utf8')
  return [...source.matchAll(/(?:import|export)\s+(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"]/g)]
    .map((match) => match[1])
    .filter((specifier) => specifier.startsWith('.'))
}

/** @param {string} path Absolute path. @returns {string} Web-root-relative path. */
function local (path) {
  return relative(WEB_ROOT, path).replaceAll('\\', '/')
}

test('browser modules obey the documented directed dependency graph', () => {
  const violations = []
  for (const sourcePath of modules()) {
    const source = local(sourcePath)
    const sourceRoot = source.split('/', 1)[0]
    for (const specifier of importsOf(sourcePath)) {
      const target = local(resolve(dirname(sourcePath), specifier.split(/[?#]/, 1)[0]))
      const targetRoot = target.split('/', 1)[0]
      const allowed = source === 'app.js' ||
        (sourceRoot === 'lib' && ['lib', 'vendor'].includes(targetRoot)) ||
        (sourceRoot === 'panels' && targetRoot === 'panels') ||
        (sourceRoot === 'render' && ['render', 'vendor'].includes(targetRoot)) ||
        (sourceRoot === 'shell' && ['shell', 'vendor'].includes(targetRoot))
      if (!allowed) violations.push(`${source} -> ${target}`)
    }
  }
  assert.deepEqual(violations, [])
})

test('only vendor adapters reach the network, and each pins a full URL', () => {
  for (const sourcePath of modules()) {
    const source = readFileSync(sourcePath, 'utf8')
    const remote = [...source.matchAll(/from\s+['"](https?:[^'"]+)['"]/g)].map((m) => m[1])
    if (local(sourcePath).startsWith('vendor/')) {
      assert.ok(remote.length > 0, `${local(sourcePath)} pins no URL`)
      for (const url of remote) assert.match(url, /@\d+\.\d+\.\d+\//, `${url} is not version-pinned`)
    } else {
      assert.deepEqual(remote, [], `${local(sourcePath)} imports from the network`)
    }
  }
})

test('the stylesheet and the script share one cache-busting release', () => {
  const index = readFileSync(resolve(WEB_ROOT, 'index.html'), 'utf8')
  const appVersion = index.match(/app\.js\?v=([^"']+)/)?.[1]
  const cssVersion = index.match(/app\.css\?v=([^"']+)/)?.[1]
  assert.ok(appVersion)
  assert.equal(cssVersion, appVersion)
})
