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

export interface ProteobenchReference {
  path: string
  document: unknown
}

// The viewer reads only files: runs under data/ and the fixture store under fixtures/, so a
// plain file server can serve both. HTTP reads stay on the viewer origin so Vite can proxy them.
function treePath (tree: 'data' | 'fixtures', path: string): string {
  return `${tree}/${path.split('/').map(encodeURIComponent).join('/')}`
}

function navigationBase (): string {
  // Directory listings contain server-root links and must open on that server.
  return import.meta.env?.DEV ? 'http://127.0.0.1:8766/' : document.baseURI
}

export function dataUrl (path: string): string {
  return new URL(treePath('data', path), document.baseURI).href
}

function navigationUrl (tree: 'data' | 'fixtures', path: string): string {
  const url = new URL(treePath(tree, path), navigationBase())
  if (!/\.json$/i.test(path)) url.searchParams.set('view', '1')
  return url.href
}

/** Open a run file or folder: a report, a snapshot or an artifact. */
export function fileUrl (path: string): string {
  return navigationUrl('data', path)
}

/** Open a fixture-store file or folder: a vendor table, a parameter file or a FASTA. */
export function sourceUrl (path: string): string {
  return navigationUrl('fixtures', path)
}

function isSchemaDocument (value: unknown): value is SchemaDocument {
  return typeof value === 'object' && value !== null &&
    'schema_version' in value && value.schema_version === 2
}

export async function readCatalog (): Promise<Catalog> {
  const response = await fetch(dataUrl('index.json'), { cache: 'no-store' })
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

/** Read the file or folder kind the run recorded for each selected input. */
export async function readInputKinds (context: string): Promise<Record<string, InputKind>> {
  const response = await fetch(dataUrl(`${context}/input_kinds.json`), { cache: 'no-store' })
  if (response.status === 404) return {}
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

/** Read the downloaded ProteoBench JSON the run recorded for each selected submission. */
export async function readProteobenchReferences (context: string): Promise<Map<string, ProteobenchReference>> {
  const response = await fetch(dataUrl(`${context}/proteobench_references.json`), { cache: 'no-store' })
  if (response.status === 404) return new Map()
  if (!response.ok) throw new Error(`ProteoBench references: HTTP ${response.status}`)
  const document: unknown = await response.json()
  if (!isSchemaDocument(document) || !('references' in document)) throw new Error('Unsupported ProteoBench references schema')
  const references = document.references
  if (typeof references !== 'object' || references === null || Array.isArray(references)) {
    throw new Error('Invalid ProteoBench references')
  }
  const entries = Object.entries(references).map(([input, reference]: [string, unknown]) => {
    if (typeof reference !== 'object' || reference === null || !('path' in reference) ||
      typeof reference.path !== 'string' || !('document' in reference)) {
      throw new Error(`Invalid ProteoBench reference: ${input}`)
    }
    return [input, { path: reference.path, document: reference.document }] as const
  })
  return new Map(entries)
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
