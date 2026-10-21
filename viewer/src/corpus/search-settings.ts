import type { RunSearchSettings } from './types.js'

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
