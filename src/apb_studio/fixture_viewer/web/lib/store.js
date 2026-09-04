// The store's tables joined into what the viewer shows. Pure data shaping, so this
// module is the one the Node tests exercise directly.

const FLAGS = ['smallest_per_software_version', 'smallest_per_software', 'smallest_per_module']

/**
 * Read a pandas boolean cell.
 *
 * @param {string|undefined} value The cell text.
 * @returns {boolean} True for "True".
 */
function flag (value) {
  return value === 'True' || value === 'true'
}

/**
 * Read a numeric cell, keeping absence as null.
 *
 * @param {string|undefined} value The cell text.
 * @returns {number|null} The number, or null when blank.
 */
function number (value) {
  return value === undefined || value === '' ? null : Number(value)
}

/**
 * Compose the URL of one submission's summary from the index's pattern.
 *
 * @param {string} pattern The index's `submissionSummary` pattern.
 * @param {object} row A catalog row.
 * @returns {string} The store-relative path of that submission's summary.
 */
export function summaryPath (pattern, row) {
  return pattern
    .replace('{repo_name}', row.repo_name)
    .replace('{intermediate_hash}', row.intermediate_hash)
}

/**
 * Join the catalogue with each submission's own summary document.
 *
 * A submission is downloaded when its summary is there, and that is the whole test: the
 * summary is written beside the files as they land, so no table has to be aggregated and
 * no listing refreshed. downloads.csv is consulted only for what a summary cannot say —
 * a hash the server never served.
 *
 * @param {object[]} catalog Rows of catalog.csv.
 * @param {object[]} downloads Rows of downloads.csv.
 * @param {Map<string, object|null>} summaries Summary documents by submission hash.
 * @returns {object[]} One typed row per catalogued submission.
 */
export function joinSubmissions (catalog, downloads, summaries) {
  const downloaded = new Map(downloads.map((row) => [row.intermediate_hash, row]))
  return catalog.map((row) => {
    const download = downloaded.get(row.intermediate_hash)
    const summary = summaries.get(row.intermediate_hash)
    const refused = download && download.status !== 'ok' ? download.status : 'not downloaded'
    return {
      module: row.module,
      repo_name: row.repo_name,
      intermediate_hash: row.intermediate_hash,
      software_name: row.software_name,
      software_version: row.software_version,
      nr_feature: number(row.nr_feature),
      is_temporary: flag(row.is_temporary),
      old_new: row.old_new,
      ...Object.fromEntries(FLAGS.map((name) => [name, flag(row[name])])),
      status: summary ? 'ok' : refused,
      input_file: summary?.input_file ?? '',
      size_mb: summary ? summary.size_bytes / 1e6 : null,
      format: summary?.format ?? '',
      delimiter: summary?.delimiter ?? '',
      rows: summary?.rows ?? null,
      columns: summary?.columns ?? null,
      column_names: summary?.column_names ?? '',
      parameter_file: summary?.parameter_file ?? '',
      downloaded_at: summary?.downloaded_at ?? '',
      // The day alone, for grouping: 202 timestamps to the second are 202 groups.
      downloaded_on: (summary?.downloaded_at ?? '').slice(0, 10)
    }
  })
}

/**
 * Turn the store index and the loaded summaries into labelled facts.
 *
 * @param {object|null} index The index.json document.
 * @param {object[]} downloaded Summary documents of the submissions on disk.
 * @returns {Array<{key: string, value: string}>} Key/value rows.
 */
export function storageRows (index, downloaded = []) {
  if (!index) return [{ key: 'Store', value: 'index.json not available' }]
  const gb = (bytes) => `${(bytes / 1e9).toFixed(2)} GB`
  const bytes = downloaded.reduce((total, summary) => total + (summary.size_bytes ?? 0), 0)
  return [
    { key: 'Store root', value: index.root },
    { key: 'Submissions on disk', value: String(downloaded.length) },
    { key: 'Vendor tables size', value: gb(bytes) },
    { key: 'Metadata size', value: gb(index.bytes?.metadata ?? 0) },
    { key: 'FASTA files', value: (index.fasta ?? []).join(', ') || 'none' },
    { key: 'FASTA size', value: gb(index.bytes?.fasta ?? 0) },
    { key: 'Module TOMLs', value: (index.modules ?? []).join(', ') || 'none' },
    ...(index.tables ?? []).map((table) => ({
      key: table.name,
      value: `${(table.sizeBytes / 1e3).toFixed(1)} kB`
    }))
  ]
}

/**
 * Parse one ProteoBench submission document.
 *
 * ProteoBench writes a bare `NaN` where a value is missing, which JSON has no literal for
 * and `JSON.parse` refuses. Those tokens become null; the Python catalogue reader treats
 * them the same way.
 *
 * @param {string} text The document's text, empty when the file is absent.
 * @returns {object|null} The parsed document, or null for empty text.
 */
export function parseSubmissionJson (text) {
  if (!text.trim()) return null
  return JSON.parse(text.replace(/:\s*(NaN|-?Infinity)\s*(?=[,}\]])/g, ': null'))
}
