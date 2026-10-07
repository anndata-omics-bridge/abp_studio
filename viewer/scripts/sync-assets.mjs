import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const viewer = fileURLToPath(new URL('../', import.meta.url))
const distribution = resolve(viewer, 'dist')
const manifest = JSON.parse(await readFile(resolve(distribution, '.vite/manifest.json'), 'utf8'))
const check = process.argv.includes('--check')

function assetsFor (entry, seen = new Set()) {
  if (seen.has(entry)) return new Set()
  seen.add(entry)
  const chunk = manifest[entry]
  if (!chunk) throw new Error(`Build manifest is missing ${entry}`)
  const assets = new Set([chunk.file, ...(chunk.css ?? []), ...(chunk.assets ?? [])])
  for (const dependency of [...(chunk.imports ?? []), ...(chunk.dynamicImports ?? [])]) {
    for (const asset of assetsFor(dependency, seen)) assets.add(asset)
  }
  return assets
}

async function filesUnder (directory, prefix = '') {
  const files = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = prefix + entry.name
    if (entry.isDirectory()) files.push(...await filesUnder(resolve(directory, entry.name), `${path}/`))
    else files.push(path)
  }
  return files
}

for (const name of ['corpus', 'fixture']) {
  const destination = resolve(viewer, `../src/apb_studio/${name}_viewer/web`)
  const entry = `${name}/index.html`
  const files = new Map()
  for (const asset of assetsFor(entry)) {
    if (asset !== entry) files.set(asset, await readFile(resolve(distribution, asset)))
  }
  const index = await readFile(resolve(distribution, entry), 'utf8')
  files.set('index.html', Buffer.from(index.replaceAll('../assets/', './assets/')))
  if (check) {
    const packaged = await filesUnder(destination)
    const stale = packaged.filter(path => !files.has(path))
    for (const [path, expected] of files) {
      if (!packaged.includes(path) || !expected.equals(await readFile(resolve(destination, path)))) stale.push(path)
    }
    if (stale.length) throw new Error(`${name} viewer bundles are stale: ${stale.join(', ')}; run make build-web`)
    console.log(`${name} viewer bundles match TypeScript sources (${files.size} files)`)
  } else {
    await rm(destination, { recursive: true, force: true })
    for (const [path, content] of files) {
      const target = resolve(destination, path)
      await mkdir(dirname(target), { recursive: true })
      await writeFile(target, content)
    }
    console.log(`Packaged ${name} viewer (${files.size} files)`)
  }
}
