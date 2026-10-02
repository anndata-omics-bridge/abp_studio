import { csvParse, tsvParse } from '../vendor/d3-dsv.js'

// HTTP reads for the live catalog and persisted run files. Presentation modules
// receive the returned plain objects and never call fetch themselves.

/** @param {string} path Store-relative path. @returns {string} Absolute URL. */
export function dataUrl (path) {
  return new URL(`data/${path.split('/').map(encodeURIComponent).join('/')}`, document.baseURI).href
}

/** @param {string} path Store-relative file or folder. @returns {string} File navigation URL. */
export function fileUrl (path) {
  const url = new URL(dataUrl(path))
  if (!/\.json$/i.test(path)) url.searchParams.set('view', '1')
  return url.href
}

/** @param {string} context Run/configuration directory. @param {string} path Frozen source path. */
export function sourceUrl (context, path) {
  const url = new URL('api/source', document.baseURI)
  url.searchParams.set('context', context)
  url.searchParams.set('path', path)
  return url.href
}

/** @param {string} path API-relative path. @returns {string} Absolute URL. */
function apiUrl (path) { return new URL(`api/${path}`, document.baseURI).href }

/** @returns {Promise<object>} The live server catalog. */
export async function readCatalog () {
  const response = await fetch(apiUrl('catalog'), { cache: 'no-store' })
  if (!response.ok) throw new Error(`catalog: HTTP ${response.status}`)
  const document = await response.json()
  if (document.schema_version !== 2) throw new Error('Unsupported catalog schema')
  return document
}

/**
 * Read one persisted store file.
 *
 * @param {string} path Store-relative path.
 * @param {'json'|'csv'|'tsv'|'text'} kind Representation to return.
 * @returns {Promise<object|object[]|string|null>} Parsed content, or null for 404.
 */
export async function readStore (path, kind = 'json') {
  const response = await fetch(dataUrl(path), { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  if (kind === 'json') {
    const document = await response.json()
    if (document.schema_version !== 2) throw new Error(`Unsupported schema: ${path}`)
    return document
  }
  const text = await response.text()
  if (kind === 'csv') return csvParse(text)
  if (kind === 'tsv') return tsvParse(text)
  return text
}

/** @param {string} path Store-relative path. @returns {Promise<object|null>} Raw JSON. */
export async function readStoreJson (path) {
  const response = await fetch(dataUrl(path), { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return response.json()
}
