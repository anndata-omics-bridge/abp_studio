import type { DatasetRow } from '../types.js'
import type { FlowArtifact, FlowStep } from '../workflow-flow.js'
import { workflowFlow } from '../workflow-flow.js'
import { formatBytes } from '../model.js'
import { artifactStorePath } from '../representation.js'
import { fileUrl, sourceUrl } from '../lib/fetch.js'
import { columnTitle, node } from './dom.js'
import { fileLink } from './links.js'

const SUPPORTING_ROLES = new Set(['representation', 'tool_timings'])
const SOURCE_FIELDS: Record<string, string> = {
  vendor_table: 'input_file', vendor_parameter_file: 'vendor_parameter_file', fasta: 'fasta'
}
const ROLE_NAMES: Record<string, string> = {
  vendor_table: 'Vendor data', vendor_parameter_file: 'Parameters', fasta: 'FASTA',
  converted: 'Converted data', result: 'Result', export: 'Export',
  representation: 'APB representation', tool_timings: 'Tool timings'
}

function sourcePath (row: DatasetRow, item: FlowArtifact): string {
  const candidate = row[SOURCE_FIELDS[item.artifact.role]]
  return typeof candidate === 'string' && candidate &&
    (item.artifact.path === candidate || item.artifact.path.endsWith(`/${candidate}`))
    ? candidate : ''
}

function renderFile (row: DatasetRow, run: string, steps: FlowStep[], item: FlowArtifact, direction: 'input' | 'output'): HTMLElement {
  const { artifact, size } = item
  const source = direction === 'input' && item.producer == null ? sourcePath(row, item) : ''
  const observedSize = size ?? (source === row.input_file && formatBytes(row.input_file_size_bytes) ? Number(row.input_file_size_bytes) : null)
  const href = source
    ? sourceUrl(source)
    : item.producer != null && observedSize != null
      ? fileUrl(artifactStorePath(run, row.output_dir, artifact.path)) : ''
  const basename = artifact.path.split('/').at(-1) || artifact.path
  const entry = node('li', '', 'workflow-file')
  const name = node('strong', '', 'workflow-file-name')
  name.title = artifact.path
  const directory = artifact.format === 'parquet' || (source !== '' && source === row.input_file && row.input_file_kind === 'folder')
  name.append(href ? fileLink(href, basename, { directory }) : node('span', basename))
  const sizeLabel = direction === 'output' && observedSize == null ? 'Not observed' : formatBytes(observedSize) || 'Size unavailable'
  entry.append(name, node('span', [ROLE_NAMES[artifact.role] ?? columnTitle(artifact.role), sizeLabel].join(' · '), 'workflow-file-meta'))
  if (direction === 'input' && item.producer != null) {
    entry.append(node('span', `From step ${item.producer + 1} · ${steps[item.producer].report.name}`, 'workflow-handoff'))
  }
  if (direction === 'output' && item.consumers.length) {
    entry.append(node('span', `Used by ${item.consumers.map(index => `step ${index + 1} · ${steps[index].report.name}`).join(', ')}`, 'workflow-handoff'))
  }
  const details = node('details', '', 'workflow-file-details')
  details.append(node('summary', 'Full path'), node('code', artifact.path))
  if (observedSize != null) details.append(node('small', `${observedSize.toLocaleString()} bytes`))
  entry.append(details)
  return entry
}

function renderFiles (row: DatasetRow, run: string, steps: FlowStep[], files: FlowArtifact[], direction: 'input' | 'output'): HTMLElement {
  const list = node('ul', '', 'workflow-file-list')
  for (const file of files) list.append(renderFile(row, run, steps, file, direction))
  return list
}

/** Render ordered step cards while keeping file handoffs explicit and paths folded. */
export function renderWorkflowFiles (host: HTMLElement, row: DatasetRow, run: string) {
  host.replaceChildren()
  const steps = workflowFlow(row.record?.steps ?? [])
  host.hidden = steps.length === 0
  if (!steps.length) return
  host.append(node('p', 'Follow the file handoffs between steps. Expand Full path to see a file’s location and exact size.', 'workflow-flow-description'))
  const flow = node('ol', '', 'workflow-flow')
  steps.forEach((step, index) => {
    const item = node('li', '', 'workflow-step')
    const card = node('article', '', 'workflow-step-card')
    const header = node('header', '', 'workflow-step-header')
    const title = node('h4', `${index + 1} · ${step.report.name}`)
    const status = node('span', step.report.status, 'workflow-step-status')
    status.dataset.status = step.report.status
    header.append(title, status)
    card.append(header)
    const body = node('div', '', 'workflow-step-files')
    for (const direction of ['input', 'output'] as const) {
      const section = node('section', '', `workflow-${direction}s`)
      section.append(node('h5', direction === 'input' ? 'Inputs' : 'Outputs'))
      const files = direction === 'input' ? step.inputs : step.outputs
      const primary = files.filter(file => !SUPPORTING_ROLES.has(file.artifact.role) || file.consumers.length || (direction === 'input' && file.producer != null))
      const supporting = files.filter(file => !primary.includes(file))
      if (primary.length) section.append(renderFiles(row, run, steps, primary, direction))
      else if (!files.length) section.append(node('p', `No ${direction}s recorded`, 'empty-note'))
      if (supporting.length) {
        const details = node('details', '', 'workflow-supporting')
        details.append(node('summary', `Supporting files (${supporting.length})`), renderFiles(row, run, steps, supporting, direction))
        section.append(details)
      }
      body.append(section)
    }
    card.append(body)
    item.append(card)
    flow.append(item)
  })
  host.append(flow)
}
