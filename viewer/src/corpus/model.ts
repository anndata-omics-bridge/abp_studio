import type { Artifact, ChartPoint, ChartView, CsvRow, CsvRows, DatasetReport, DatasetRow, DirectedArtifact, Operation, RunManifest, RunChoice, CatalogRun, StepReport, TimingPoint, TimingView, ToolTimings } from './types.js'

// Pure projections of persisted documents. No filesystem or proteomics inference.
const CORPUS_FIELDS = ['input_file', 'vendor_parameter_file', 'module', 'software_name']
const AUXILIARY_OUTPUTS = new Set(['representation', 'tool_timings'])
const SCIENTIFIC_OUTPUT_ROLES = new Set(['result', 'converted', 'aggregated', 'export', 'fasta_verified'])

/** Actual persisted scientific files distinguish AnnData and MuData within the HDF5 backend. */
export function scientificOutputExtensions (reports: Iterable<DatasetReport | null | undefined>): string[] {
  const extensions = new Set<string>()
  for (const report of reports) {
    const output = finalScientificOutput(observedOutputs(report))
    const extension = output?.path.replace(/\/+$/, '').split('/').at(-1)?.match(/\.[^./]+$/)?.[0]
    if (extension) extensions.add(extension.toLowerCase())
  }
  return [...extensions].sort()
}

function matchingWorkflow (input: CsvRow, workflowRows: CsvRows): CsvRow {
  if (!workflowRows.length) return {}
  const columns = workflowRows.columns ?? Object.keys(workflowRows[0])
  const joinFields = columns.filter(field => CORPUS_FIELDS.includes(field))
  if (!joinFields.length) return {}
  const matches = workflowRows.filter(row =>
    joinFields.every(field => row[field] === input[field]))
  return matches.length === 1 ? matches[0] : {}
}

export function workflowFields (workflowRows: CsvRows): string[] {
  const columns = workflowRows.columns ?? Object.keys(workflowRows[0] ?? {})
  return columns.filter(field => !CORPUS_FIELDS.includes(field))
}

function observedOutputs (record: DatasetReport | null | undefined): Artifact[] {
  return (record?.steps ?? []).flatMap(step => step.status === 'succeeded'
    ? (step.outputs ?? []).filter(artifact =>
        !AUXILIARY_OUTPUTS.has(artifact.role) && finiteNumber(artifact.size_bytes) != null)
    : [])
}

function finalScientificOutput (outputs: Artifact[]): Artifact | undefined {
  return outputs.filter(artifact => SCIENTIFIC_OUTPUT_ROLES.has(artifact.role)).at(-1)
}

function finalObservedOutput (record: DatasetReport | null | undefined): Artifact | undefined {
  const outputs = observedOutputs(record)
  return finalScientificOutput(outputs) ?? outputs.at(-1)
}

function ionVariablesForStep (step: StepReport, representationFiles: Map<string, number | null>): number | null {
  const artifact = (step.outputs ?? []).find(output =>
    output.role === 'representation' && output.size_bytes != null)
  return artifact ? representationFiles.get(artifact.path) ?? null : null
}

function finalIonVariables (record: DatasetReport | null | undefined, representationFiles: Map<string, number | null>): number | null {
  for (const step of [...(record?.steps ?? [])].reverse()) {
    if (step.status !== 'succeeded') continue
    const artifact = (step.outputs ?? []).find(candidate =>
      candidate.role === 'representation' && candidate.size_bytes != null)
    if (artifact) return representationFiles.get(artifact.path) ?? null
  }
  return null
}

export function datasetRows (manifest: RunManifest, corpus: CsvRows, inputMetadata: CsvRows, reports: Map<string, DatasetReport>, progress: Map<string, DatasetReport | null>, operation: Operation | null, workflowRows: CsvRows = [], representationFiles: Map<string, number | null> = new Map()): DatasetRow[] {
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
        ['failed', 'interrupted'].includes(operation?.status ?? '')) status = 'interrupted'
    return {
      ...input, ...matchingWorkflow(input, workflowRows), ...metadata.get(link.input_file), ...link,
      module: input.module ?? '',
      software_name: input.software_name ?? '',
      input_file_name: link.input_file.split('/').at(-1) ?? '',
      input_file_parent: link.input_file.split('/').at(-2) ?? '',
      input_file_kind: null,
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

export function workflowSteps (rows: DatasetRow[]): string[] {
  const result: string[] = []
  for (const row of rows) {
    for (const step of row.record?.steps ?? []) {
      if (!result.includes(step.name)) result.push(step.name)
    }
  }
  return result
}

export function datasetArtifacts (row: DatasetRow): DirectedArtifact[] {
  return (row.record?.steps ?? []).flatMap(step => [
    ...(step.inputs ?? []).map(artifact => ({ ...artifact, direction: 'Input' as const, step: step.name })),
    ...(step.outputs ?? []).map(artifact => ({ ...artifact, direction: 'Output' as const, step: step.name }))
  ])
}

export function formatBytes (value: unknown): string {
  const bytes = finiteNumber(value)
  if (bytes == null || bytes < 0) return ''
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const unit = Math.min(Math.floor(Math.log(Math.max(bytes, 1)) / Math.log(1024)), units.length - 1)
  const amount = bytes / 1024 ** unit
  return `${unit === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unit]}`
}

function finiteNumber (value: unknown): number | null {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function toolName (step: StepReport): string {
  const executable = step.command?.[0]
  if (typeof executable !== 'string' || executable === '') return 'unknown tool'
  return executable.split(/[\\/]/).at(-1) || 'unknown tool'
}

function datasetPoint (row: DatasetRow) {
  return {
    input_file: row.input_file,
    module: row.module,
    software_name: row.software_name,
    input_size_mib: finiteNumber(row.input_file_size_bytes) == null
      ? null
      : Number(row.input_file_size_bytes) / 1024 ** 2
  }
}

function commonPoint (row: DatasetRow, step: StepReport, representationFiles: Map<string, number | null>): ChartPoint {
  return {
    ...datasetPoint(row),
    ion_variables: ionVariablesForStep(step, representationFiles) ?? row.ion_variables ?? null,
    step: step.name,
    tool: toolName(step),
    status: step.status,
  }
}

export function chartPoints (rows: DatasetRow[], timingFiles: Map<string, ToolTimings | null> = new Map(), representationFiles: Map<string, number | null> = new Map()): { steps: ChartPoint[]; outputs: ChartPoint[]; timings: TimingPoint[] } {
  const steps: ChartPoint[] = []
  const outputs: ChartPoint[] = []
  const timings: TimingPoint[] = []
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
          if (!document) continue
          const basename = artifact.path.split('/').at(-1)
          for (const phase of document.phases) {
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

function timingViews (points: TimingPoint[]): TimingView[] {
  const grouped = new Map<string, TimingView>()
  for (const point of points) {
    let view = grouped.get(point.timing_key)
    if (!view) {
      view = { key: point.timing_key, label: point.timing_label, points: [] }
      grouped.set(point.timing_key, view)
    }
    view.points.push(point)
  }
  return [...grouped.values()]
}

function workflowResourcePoint (row: DatasetRow): ChartPoint | null {
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

export function chartViews (rows: DatasetRow[], timingFiles: Map<string, ToolTimings | null> = new Map(), representationFiles: Map<string, number | null> = new Map()): ChartView[] {
  const points = chartPoints(rows, timingFiles, representationFiles)
  const definitions: { name: string; tool: string }[] = []
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

export function counts (rows: DatasetRow[]): Record<string, number> {
  return rows.reduce((result, row) => {
    result[row.status] = (result[row.status] ?? 0) + 1
    return result
  }, {} as Record<string, number>)
}

export function statusFractions (summary: Record<string, number>, total: number): Record<string, number> {
  return Object.fromEntries(
    ['succeeded', 'failed', 'running', 'interrupted']
      .map(status => [status, total ? (summary[status] ?? 0) / total : 0])
  )
}

export function runChoices (runs: CatalogRun[]): RunChoice[] {
  return runs.map(run => ({
    ...run,
    label: `${run.manifest.corpus_name} · ${run.manifest.workflow} · ${run.manifest.format}`
  })).sort((first, second) => first.label.localeCompare(second.label))
}
