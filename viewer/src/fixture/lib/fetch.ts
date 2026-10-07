import { csvParse } from '../../shared/d3-dsv.js'
import type { CsvRow } from '../types.js'

// Missing store files mean acquisition has not produced them yet.
async function get (url: string): Promise<Response | null> {
  const response = await fetch(url, { cache: 'no-cache' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return response
}

export async function fetchCsv (url: string): Promise<CsvRow[]> {
  const response = await get(url)
  return response ? csvParse(await response.text()) : []
}

export async function fetchJson (url: string): Promise<unknown> {
  const response = await get(url)
  return response ? response.json() : null
}

export async function fetchText (url: string): Promise<string> {
  const response = await get(url)
  return response ? response.text() : ''
}
