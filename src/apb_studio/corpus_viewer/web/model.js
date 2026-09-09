// Pure projections of persisted documents. No filesystem or proteomics inference.
const CORPUS_FIELDS = ['input_file', 'vendor_parameter_file', 'module', 'software_name']

function matchingWorkflow (input, workflowRows) {
  if (!workflowRows.length) return {}
  const columns = workflowRows.columns ?? Object.keys(workflowRows[0])
  const joinFields = columns.filter(field => CORPUS_FIELDS.includes(field))
  if (!joinFields.length) return {}
  const matches = workflowRows.filter(row =>
    joinFields.every(field => row[field] === input[field]))
  return matches.length === 1 ? matches[0] : {}
}

export function workflowFields (workflowRows) {
  const columns = workflowRows.columns ?? Object.keys(workflowRows[0] ?? {})
  return columns.filter(field => !CORPUS_FIELDS.includes(field))
}

function finalObservedOutput (record) {
  return (record?.steps ?? []).flatMap(step => step.status === 'succeeded'
    ? (step.outputs ?? []).filter(artifact =>
        artifact.role !== 'representation' && finiteNumber(artifact.size_bytes) != null)
    : []).at(-1)
}

export function datasetRows (manifest, corpus, inputMetadata, reports, progress, operation, workflowRows = []) {
  const inputs = new Map(corpus.map(row => [row.input_file, row]))
  const metadata = new Map(inputMetadata.map(row => [row.input_file, row]))
  return manifest.reports.map(link => {
    const input = inputs.get(link.input_file) ?? {}
    const final = reports.get(link.path)
    const live = progress.get(link.progress)
    const record = final ?? live
    const output = finalObservedOutput(record)
    let status = record?.status ?? 'pending'
    if (!final && ['running', 'pending'].includes(status) &&
        ['failed', 'interrupted'].includes(operation?.status)) status = 'interrupted'
    return {
      ...input, ...matchingWorkflow(input, workflowRows), ...metadata.get(link.input_file), ...link,
      input_file_name: link.input_file.split('/').at(-1),
      input_file_parent: link.input_file.split('/').at(-2) ?? '',
      output_file: output?.path ?? '',
      output_file_name: output?.path?.split('/').at(-1) ?? '',
      output_file_parent: output?.path?.split('/').at(-2) ?? '',
      output_file_size_bytes: output?.size_bytes ?? null,
      status,
      runtime_seconds: record?.runtime_seconds ?? null,
      peak_memory_bytes: record?.steps.reduce((peak, step) => Math.max(peak, step.peak_memory_bytes ?? 0), 0) || null,
      record
    }
  })
}

export function workflowSteps (rows) {
  const result = []
  for (const row of rows) {
    for (const step of row.record?.steps ?? []) {
      if (!result.includes(step.name)) result.push(step.name)
    }
  }
  return result
}

export function datasetArtifacts (row) {
  return (row.record?.steps ?? []).flatMap(step => [
    ...(step.inputs ?? []).map(artifact => ({ ...artifact, direction: 'Input', step: step.name })),
    ...(step.outputs ?? []).map(artifact => ({ ...artifact, direction: 'Output', step: step.name }))
  ])
}

export function formatBytes (value) {
  const bytes = finiteNumber(value)
  if (bytes == null || bytes < 0) return ''
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const unit = Math.min(Math.floor(Math.log(Math.max(bytes, 1)) / Math.log(1024)), units.length - 1)
  const amount = bytes / 1024 ** unit
  return `${unit === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unit]}`
}

function finiteNumber (value) {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function commonPoint (row, step) {
  return {
    input_file: row.input_file,
    module: row.module,
    software_name: row.software_name,
    step: step.name,
    status: step.status,
    input_size_mib: finiteNumber(row.input_file_size_bytes) == null
      ? null
      : Number(row.input_file_size_bytes) / 1024 ** 2
  }
}

export function chartPoints (rows) {
  const steps = []
  const outputs = []
  for (const row of rows) {
    for (const step of row.record?.steps ?? []) {
      const common = commonPoint(row, step)
      const runtime = finiteNumber(step.runtime_seconds)
      const memory = finiteNumber(step.peak_memory_bytes)
      if (runtime != null || memory != null) {
        steps.push({
          ...common,
          runtime_seconds: runtime,
          peak_memory_mib: memory == null ? null : memory / 1024 ** 2
        })
      }
      for (const artifact of step.outputs ?? []) {
        if (artifact.role === 'representation') continue
        const size = finiteNumber(artifact.size_bytes)
        if (size == null) continue
        outputs.push({
          ...common,
          output_role: artifact.role,
          output_path: artifact.path,
          output_size_mib: size / 1024 ** 2
        })
      }
    }
  }
  return { steps, outputs }
}

export function counts (rows) {
  return rows.reduce((result, row) => {
    result[row.status] = (result[row.status] ?? 0) + 1
    return result
  }, {})
}

export function statusFractions (summary, total) {
  return Object.fromEntries(
    ['succeeded', 'failed', 'running', 'interrupted']
      .map(status => [status, total ? (summary[status] ?? 0) / total : 0])
  )
}

export function executionGroups (runs, settings) {
  const groups = new Map()
  for (const [id, config] of settings) {
    groups.set(id, {
      id, settings: config, runs: [],
      label: `${config.workflow} · ${config.corpus.split('/').at(-1)} · ${config.format} · ${config.cores} cores · ${id.slice(0, 6)}`
    })
  }
  for (const run of runs) {
    const id = run.manifest.settings_id
    if (!id || !groups.has(id)) continue
    groups.get(id).runs.push(run)
  }
  return [...groups.values()].sort((a, b) => {
    const first = a.runs[0]?.manifest.created_at ?? ''
    const second = b.runs[0]?.manifest.created_at ?? ''
    return second.localeCompare(first)
  })
}
