import type { DatasetRow, RunChoice } from './types.js'

export const RUN_FACETS = [
  ['corpus', 'Corpus'],
  ['workflow', 'Workflow'],
  ['format', 'Format']
] as const

export const DATASET_FACETS = [
  ['software_name', 'Software'],
  ['module', 'Module'],
  ['status', 'Result'],
  ['oddity_state', 'Oddities']
] as const

type RunFacet = typeof RUN_FACETS[number][0]
type DatasetFacet = typeof DATASET_FACETS[number][0]

export interface RunFilters {
  search: string
  corpus: string[]
  workflow: string[]
  format: string[]
}

export interface DatasetFilters {
  search: string
  software_name: string[]
  module: string[]
  status: string[]
  oddity_state: string[]
}

export interface FacetOption { value: string; count: number }
export interface FacetGroup<F extends string = string> {
  key: F
  label: string
  options: FacetOption[]
}

export function emptyRunFilters (): RunFilters {
  return { search: '', corpus: [], workflow: [], format: [] }
}

export function emptyDatasetFilters (): DatasetFilters {
  return { search: '', software_name: [], module: [], status: [], oddity_state: [] }
}

function searchTokens (search: string): string[] {
  return search.toLowerCase().split(/\s+/).filter(Boolean)
}

function scalarText (values: unknown[]): string {
  return values.filter(value =>
    typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
  ).join(' ').toLowerCase()
}

function runText (run: RunChoice): string {
  return scalarText([
    run.label, run.path, ...(run.outputExtensions ?? []), ...Object.values(run.manifest),
    ...Object.keys(run.manifest.tools ?? {}),
    ...Object.values(run.manifest.tools ?? {}),
    ...Object.values(run.manifest.tool_versions ?? {})
  ])
}

function datasetText (row: DatasetRow): string {
  return scalarText(Object.values(row))
}

function runValue (run: RunChoice, facet: RunFacet): string {
  return facet === 'corpus' ? run.manifest.corpus_name : run.manifest[facet]
}

function datasetValue (row: DatasetRow, facet: DatasetFacet): string {
  return row[facet] ?? 'Not summarized'
}

type FacetDefinitions<F extends string> = readonly (readonly [F, string])[]
type Filters<F extends string> = { search: string } & Record<F, string[]>

function matches<T, F extends string> (item: T, tokens: string[], filters: Filters<F>, facets: FacetDefinitions<F>, text: (item: T) => string, value: (item: T, facet: F) => string, excluded?: F): boolean {
  const haystack = text(item)
  return tokens.every(token => haystack.includes(token)) && facets.every(([facet]) =>
    facet === excluded || !filters[facet].length || filters[facet].includes(value(item, facet))
  )
}

function filterItems<T, F extends string> (items: T[], filters: Filters<F>, facets: FacetDefinitions<F>, text: (item: T) => string, value: (item: T, facet: F) => string): T[] {
  const tokens = searchTokens(filters.search)
  return items.filter(item => matches(item, tokens, filters, facets, text, value))
}

function facetGroups<T, F extends string> (items: T[], filters: Filters<F>, facets: FacetDefinitions<F>, text: (item: T) => string, value: (item: T, facet: F) => string): FacetGroup<F>[] {
  const tokens = searchTokens(filters.search)
  return facets.map(([facet, label]) => {
    const counts = new Map<string, number>(filters[facet].map(selected => [selected, 0]))
    for (const item of items) {
      const option = value(item, facet)
      const count = counts.get(option) ?? 0
      counts.set(option, count + Number(matches(item, tokens, filters, facets, text, value, facet)))
    }
    return {
      key: facet,
      label,
      options: [...counts].sort(([first], [second]) => first.localeCompare(second, undefined, { numeric: true }))
        .map(([value, count]) => ({ value, count }))
    }
  })
}

export function filterRuns (runs: RunChoice[], filters: RunFilters): RunChoice[] {
  return filterItems(runs, filters, RUN_FACETS, runText, runValue)
}

export function runFacets (runs: RunChoice[], filters: RunFilters): FacetGroup<RunFacet>[] {
  return facetGroups(runs, filters, RUN_FACETS, runText, runValue)
}

export function filterDatasets (rows: DatasetRow[], filters: DatasetFilters): DatasetRow[] {
  return filterItems(rows, filters, DATASET_FACETS, datasetText, datasetValue)
}

export function datasetFacets (rows: DatasetRow[], filters: DatasetFilters): FacetGroup<DatasetFacet>[] {
  return facetGroups(rows, filters, DATASET_FACETS, datasetText, datasetValue)
}
