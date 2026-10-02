// Pure projections of persisted documents. No filesystem or proteomics inference.
const CORPUS_FIELDS = ['input_file', 'vendor_parameter_file', 'module', 'software_name']
const AUXILIARY_OUTPUTS = new Set(['representation', 'tool_timings'])

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
        !AUXILIARY_OUTPUTS.has(artifact.role) && finiteNumber(artifact.size_bytes) != null)
    : []).at(-1)
}

function ionVariablesForStep (step, representationFiles) {
  const artifact = (step.outputs ?? []).find(output =>
    output.role === 'representation' && output.size_bytes != null)
  return artifact ? representationFiles.get(artifact.path) ?? null : null
}

function finalIonVariables (record, representationFiles) {
  for (const step of [...(record?.steps ?? [])].reverse()) {
    if (step.status !== 'succeeded') continue
    const artifact = (step.outputs ?? []).find(candidate =>
      candidate.role === 'representation' && candidate.size_bytes != null)
    if (artifact) return representationFiles.get(artifact.path) ?? null
  }
  return null
}

export function datasetRows (manifest, corpus, inputMetadata, reports, progress, operation, workflowRows = [], representationFiles = new Map()) {
  const inputs = new Map(corpus.map(row => [row.input_file, row]))
  const metadata = new Map(inputMetadata.map(row => [row.input_file, row]))
  return manifest.reports.map(link => {
    const input = inputs.get(link.input_file) ?? {}
    const final = reports.get(link.path)
    const live = progress.get(link.progress)
    const record = final ?? live
    const output = finalObservedOutput(record)
    const ionVariables = finalIonVariables(record, representationFiles)
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
      output_file_format: output?.format ?? null,
      ion_variables: ionVariables,
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

function toolName (step) {
  const executable = step.command?.[0]
  if (typeof executable !== 'string' || executable === '') return 'unknown tool'
  return executable.split(/[\\/]/).at(-1) || 'unknown tool'
}

function datasetPoint (row) {
  return {
    input_file: row.input_file,
    module: row.module,
    software_name: row.software_name,
    input_size_mib: finiteNumber(row.input_file_size_bytes) == null
      ? null
      : Number(row.input_file_size_bytes) / 1024 ** 2
  }
}

function commonPoint (row, step, representationFiles) {
  return {
    ...datasetPoint(row),
    ion_variables: ionVariablesForStep(step, representationFiles) ?? row.ion_variables ?? null,
    step: step.name,
    tool: toolName(step),
    status: step.status,
  }
}

export function chartPoints (rows, timingFiles = new Map(), representationFiles = new Map()) {
  const steps = []
  const outputs = []
  const timings = []
  for (const row of rows) {
    for (const step of row.record?.steps ?? []) {
      const common = commonPoint(row, step, representationFiles)
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
        if (artifact.role === 'tool_timings' && step.status === 'succeeded') {
          const document = timingFiles.get(artifact.path)
          const basename = artifact.path.split('/').at(-1)
          for (const phase of document?.phases ?? []) {
            timings.push({
              ...common,
              timing_key: JSON.stringify([document.tool, document.operation, basename]),
              timing_label: `${document.tool} · ${document.operation}`,
              timing_path: artifact.path,
              phase: phase.name,
              duration_seconds: phase.seconds
            })
          }
        }
        if (AUXILIARY_OUTPUTS.has(artifact.role)) continue
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
  return { steps, outputs, timings }
}

function timingViews (points) {
  const grouped = new Map()
  for (const point of points) {
    if (!grouped.has(point.timing_key)) {
      grouped.set(point.timing_key, {
        key: point.timing_key,
        label: point.timing_label,
        points: []
      })
    }
    grouped.get(point.timing_key).points.push(point)
  }
  return [...grouped.values()]
}

function workflowResourcePoint (row) {
  const steps = row.record?.steps ?? []
  const runtimes = steps.map(step => finiteNumber(step.runtime_seconds)).filter(value => value != null)
  const memories = steps.map(step => finiteNumber(step.peak_memory_bytes)).filter(value => value != null)
  if (!runtimes.length && !memories.length) return null
  return {
    ...datasetPoint(row),
    ion_variables: row.ion_variables ?? null,
    step: 'workflow',
    tool: 'all tools',
    status: row.status ?? row.record?.status ?? 'pending',
    runtime_seconds: runtimes.length ? runtimes.reduce((total, value) => total + value, 0) : null,
    peak_memory_mib: memories.length ? Math.max(...memories) / 1024 ** 2 : null
  }
}

export function chartViews (rows, timingFiles = new Map(), representationFiles = new Map()) {
  const points = chartPoints(rows, timingFiles, representationFiles)
  const definitions = []
  const known = new Set()
  for (const row of rows) {
    for (const step of row.record?.steps ?? []) {
      if (known.has(step.name)) continue
      known.add(step.name)
      definitions.push({ name: step.name, tool: toolName(step) })
    }
  }
  return [
    {
      key: 'workflow',
      label: 'Workflow',
      steps: rows.map(workflowResourcePoint).filter(point => point != null),
      outputs: points.outputs
    },
    ...definitions.map(definition => ({
      key: `step:${definition.name}`,
      label: `${definition.name} · ${definition.tool}`,
      steps: points.steps.filter(point => point.step === definition.name),
      outputs: points.outputs.filter(point => point.step === definition.name),
      timingViews: timingViews(points.timings.filter(point => point.step === definition.name))
    }))
  ]
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

export function runChoices (runs) {
  return runs.map(run => ({
    ...run,
    label: `${run.manifest.corpus_name} · ${run.manifest.workflow} · ${run.manifest.format}`
  })).sort((first, second) => first.label.localeCompare(second.label))
}
