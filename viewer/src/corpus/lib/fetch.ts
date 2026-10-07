import { csvParse, tsvParse } from '../../shared/d3-dsv.js'
import type { CsvRows, InputKind } from '../types.js'

export interface SchemaDocument {
  schema_version: number
}

export interface Catalog extends SchemaDocument {
  schema_version: 2
  store_root?: string
  runs: string[]
  output_extensions?: Record<string, string[]>
}

// HTTP reads stay on the viewer origin so Vite can proxy them in development.
function dataPath (path: string): string {
  return `data/${path.split('/').map(encodeURIComponent).join('/')}`
}

function navigationBase (): string {
  // Directory listings contain server-root links and must open on that server.
  return import.meta.env?.DEV ? 'http://127.0.0.1:8766/' : document.baseURI
}

export function dataUrl (path: string): string {
  return new URL(dataPath(path), document.baseURI).href
}

export function fileUrl (path: string): string {
  const url = new URL(dataPath(path), navigationBase())
  if (!/\.json$/i.test(path)) url.searchParams.set('view', '1')
  return url.href
}

export function sourceUrl (context: string, path: string): string {
  const url = new URL('api/source', navigationBase())
  url.searchParams.set('context', context)
  url.searchParams.set('path', path)
  return url.href
}

export function proteobenchReferenceUrl (context: string, input: string): string {
  const url = new URL('api/proteobench-reference', navigationBase())
  url.searchParams.set('context', context)
  url.searchParams.set('input', input)
  return url.href
}

function apiUrl (path: string): string {
  return new URL(`api/${path}`, document.baseURI).href
}

function isSchemaDocument (value: unknown): value is SchemaDocument {
  return typeof value === 'object' && value !== null &&
    'schema_version' in value && value.schema_version === 2
}

export async function readCatalog (): Promise<Catalog> {
  const response = await fetch(apiUrl('catalog'), { cache: 'no-store' })
  if (!response.ok) throw new Error(`catalog: HTTP ${response.status}`)
  const document: unknown = await response.json()
  if (!isSchemaDocument(document)) throw new Error('Unsupported catalog schema')
  if (!('runs' in document) || !Array.isArray(document.runs) ||
    !document.runs.every((path: unknown) => typeof path === 'string')) {
    throw new Error('Invalid catalog run paths')
  }
  if ('store_root' in document && typeof document.store_root !== 'string') {
    throw new Error('Invalid catalog store root')
  }
  if ('output_extensions' in document) {
    const extensions = document.output_extensions
    if (typeof extensions !== 'object' || extensions === null || Array.isArray(extensions) ||
      !Object.values(extensions).every(value => Array.isArray(value) && value.every(extension => typeof extension === 'string'))) {
      throw new Error('Invalid catalog output extensions')
    }
  }
  return document as Catalog
}

/** Read filesystem kinds for the selected run's frozen inputs without loading their contents. */
export async function readInputKinds (context: string): Promise<Record<string, InputKind>> {
  const url = new URL(apiUrl('input-kinds'))
  url.searchParams.set('context', context)
  const response = await fetch(url.href, { cache: 'no-store' })
  if (!response.ok) throw new Error(`input kinds: HTTP ${response.status}`)
  const document: unknown = await response.json()
  if (!isSchemaDocument(document) || !('input_kinds' in document)) throw new Error('Unsupported input kinds schema')
  const kinds = document.input_kinds
  if (typeof kinds !== 'object' || kinds === null || Array.isArray(kinds) ||
      !Object.values(kinds).every(value => value === 'file' || value === 'folder')) {
    throw new Error('Invalid input kinds')
  }
  return kinds as Record<string, InputKind>
}

/** Read downloaded scores for the exact input in the selected run's snapshot. */
export async function readProteobenchReference (context: string, input: string): Promise<unknown> {
  const url = new URL(apiUrl('proteobench-reference'))
  url.searchParams.set('context', context)
  url.searchParams.set('input', input)
  const response = await fetch(url.href, { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`ProteoBench reference: HTTP ${response.status}`)
  return response.json()
}

/** Empty snapshots retain their CSV headers for the table adapter. */
export function emptyCsv (): CsvRows {
  return Object.assign([], { columns: [] })
}

export async function readStore<T = SchemaDocument> (path: string, kind?: 'json'): Promise<T | null>
export async function readStore (path: string, kind: 'csv' | 'tsv'): Promise<CsvRows | null>
export async function readStore (path: string, kind: 'text'): Promise<string | null>
export async function readStore (path: string, kind: 'json' | 'csv' | 'tsv' | 'text' = 'json'): Promise<SchemaDocument | CsvRows | string | null> {
  const response = await fetch(dataUrl(path), { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  if (kind === 'json') {
    const document: unknown = await response.json()
    if (!isSchemaDocument(document)) throw new Error(`Unsupported schema: ${path}`)
    return document
  }
  const text = await response.text()
  if (kind === 'csv') return csvParse(text)
  if (kind === 'tsv') return tsvParse(text)
  return text
}

/** Representation and timing sidecars define their own validators. */
export async function readStoreJson (path: string): Promise<unknown> {
  const response = await fetch(dataUrl(path), { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return response.json()
}
