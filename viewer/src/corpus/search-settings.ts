import type { ParameterValue, Representation, RunSearchSettings, SearchParametersRecord, SearchedModification } from './types.js'

// The article's Figure S1 ramp, from no recorded dataset to all of them.
const EMPTY = [0xF0, 0xF3, 0xF6]
const FULL = [0x2C, 0x47, 0x5E]

export interface SearchSettingsCell { percent: number; text: string; colour: string; inverse: boolean }
export interface SearchSettingsRow { label: string; cells: SearchSettingsCell[] }

/** The summary owns the counts; the browser only validates its envelope. */
export function validatedSearchSettings (document: unknown, runId: string): RunSearchSettings {
  const header = document && typeof document === 'object' ? document as Record<string, unknown> : {}
  if (header.format !== 'apb-studio-search-settings' || header.format_version !== 1 || header.run_id !== runId ||
      !Array.isArray(header.settings) || !Array.isArray(header.datasets) || !Array.isArray(header.software)) {
    throw new Error('Unsupported or mismatched search settings summary')
  }
  return header as unknown as RunSearchSettings
}

export function rampColour (percent: number): string {
  const share = Math.min(Math.max(percent, 0), 100) / 100
  return `rgb(${EMPTY.map((empty, index) => Math.round(empty + (FULL[index] - empty) * share)).join(', ')})`
}

/** One row per software with recorded datasets, labelled with their count; text only below 100%. */
export function searchSettingsRows (summary: RunSearchSettings): SearchSettingsRow[] {
  return summary.software.filter(software => software.recorded_count > 0).map(software => ({
    label: `${software.software_name} (${software.recorded_count})`,
    cells: summary.settings.map(setting => {
      const percent = 100 * (software.recovered[setting.name] ?? 0) / software.recorded_count
      return { percent, text: percent < 100 ? percent.toFixed(0) : '', colour: rampColour(percent), inverse: percent > 55 }
    })
  }))
}

const ACRONYMS: Record<string, string> = { fdr: 'FDR', psm: 'PSM', mz: 'm/z' }

/** The parameter file apb2 recorded in a result's root part, if it read one. */
export function searchParametersRecord (representation: Representation): SearchParametersRecord | null {
  return representation.root?.apb?.parse?.provenance?.search_parameters ?? null
}

/** One row per recorded field, in apb2's order, its value as text. */
export function parameterRows (parameters: Record<string, ParameterValue>): [string, string][] {
  return Object.entries(parameters).map(([name, value]) => [settingLabel(name), parameterText(value)])
}

function settingLabel (name: string): string {
  const label = name.split('_').map(word => ACRONYMS[word] ?? word).join(' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

function parameterText (value: ParameterValue): string {
  if (value === null || value === '') return 'Not recorded'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (Array.isArray(value)) return value.length ? value.map(modificationText).join('; ') : 'None listed'
  if (typeof value === 'object') return value.mode === 'automatic' ? 'automatic' : `${value.value} ${value.unit}`
  return String(value)
}

function modificationText (modification: SearchedModification): string {
  const where = [modification.target, modification.position === 'Anywhere' ? null : modification.position]
    .filter(Boolean).join(', ')
  return where ? `${modification.name} (${where})` : modification.name
}
