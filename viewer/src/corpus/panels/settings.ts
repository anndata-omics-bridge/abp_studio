import type { ColumnDefinition, Options, Tabulator } from '../../shared/tabulator.js'
import type { CsvRows, RunManifest } from '../types.js'
import type { CorpusApp } from '../shell/corpus-app.js'

export interface ExecutionSettings { schema_version: 2; corpus: string }
export interface SettingsRun {
  directory: string
  storeRoot: string
  manifest: RunManifest
  config: ExecutionSettings
  corpus: CsvRows
  inputMetadata: CsvRows
  workflowRows: CsvRows
}

import { emptyCsv, fileUrl, readStore, sourceUrl } from '../lib/fetch.js'
import { renderJson } from '../render/dom.js'
import { fileLink } from '../render/links.js'
import { mountTable } from '../render/tabulator.js'

const tableOptions: Options = {
  height: '55vh',
  placeholder: 'No records',
  columnDefaults: { formatter: 'plaintext', headerFilter: 'input' }
}

function columnsFor (rows: CsvRows): ColumnDefinition[] {
  return (rows.columns ?? Object.keys(rows[0] ?? {})).map(field => {
    if (!['input_file', 'vendor_parameter_file', 'fasta'].includes(field)) {
      return { title: field, field }
    }
    return {
      title: field,
      field,
      formatter: cell => {
        const path: unknown = cell.getValue()
        if (typeof path !== 'string' || !path) return ''
        return fileLink(sourceUrl(path), path)
      }
    }
  })
}

function renderLinks (target: HTMLElement, directory: string, names: (string | null | undefined)[]) {
  const links = [...new Set(names.filter((name): name is string => typeof name === 'string' && Boolean(name)))].map(name => {
    const link = fileLink(fileUrl(`${directory}/${name}`), name)
    link.title = `${directory}/${name}`
    return link
  })
  target.replaceChildren(...links)
}

/** Own the Settings & inputs panel and its Tabulator handles. */
export function createSettingsPanel (app: CorpusApp) {
  let tables: Tabulator[] = []
  const host = (id: string) => app.hostFor(id)
  const linkHosts = ['execution-settings', 'saved-run', 'corpus-input', 'input-metadata', 'workflow-input', 'workflow-source']

  function destroy () {
    for (const table of tables) table.destroy()
    tables = []
  }

  function clear () {
    destroy()
    for (const id of ['manifest', 'run-manifest', 'corpus', 'input-metadata-table', 'workflow-table', 'source', ...linkHosts.map(id => `${id}-links`)]) {
      host(id).replaceChildren()
    }
    host('corpus-description').textContent = ''
  }

  async function showTable (id: string, rows: CsvRows) {
    const table = await mountTable(host(id), rows, columnsFor(rows), tableOptions)
    tables.push(table)
  }

  async function renderRun ({ directory, storeRoot, manifest, config, corpus, inputMetadata, workflowRows }: SettingsRun) {
    destroy()
    renderJson(host('manifest'), config)
    renderJson(host('run-manifest'), {
      run_id: manifest.run_id,
      created_at: manifest.created_at,
      artifacts_directory: `${storeRoot}/${directory}/artifacts`,
      tools: manifest.tools ?? null,
      tool_versions: manifest.tool_versions ?? null,
      corpus_snapshot: `${directory}/${manifest.source_corpus}`,
      selected_corpus_snapshot: `${directory}/${manifest.corpus}`,
      workflow_table_snapshot: manifest.workflow_table
        ? `${directory}/${manifest.workflow_table}`
        : null,
      input_metadata_snapshot: manifest.input_metadata
        ? `${directory}/${manifest.input_metadata}`
        : null
    })
    renderLinks(host('execution-settings-links'), directory, [manifest.execution_settings])
    renderLinks(host('saved-run-links'), directory, ['run.json'])
    renderLinks(host('corpus-input-links'), directory, [manifest.source_corpus, manifest.corpus])
    renderLinks(host('input-metadata-links'), directory, [manifest.input_metadata])
    renderLinks(host('workflow-input-links'), directory, [manifest.workflow_table])
    renderLinks(host('workflow-source-links'), directory, [manifest.workflow_source])
    const inventory = await readStore(`${directory}/${manifest.source_corpus}`, 'csv') ?? emptyCsv()
    host('corpus-title').textContent = `Corpus: ${config.corpus.split('/').at(-1)}`
    host('corpus-description').textContent =
      `${inventory.length} inventory entries · ${corpus.length} selected for this run. ` +
      'This is the frozen run snapshot.'
    await showTable('corpus', inventory)
    host('input-metadata-table').replaceChildren()
    if (manifest.input_metadata) {
      host('input-metadata-title').textContent = `Input sizes: ${manifest.input_metadata}`
      await showTable('input-metadata-table', inputMetadata)
    } else {
      host('input-metadata-title').textContent = 'No input-size snapshot in this run'
    }
    host('workflow-table').replaceChildren()
    if (manifest.workflow_table) {
      host('workflow-table-title').textContent = manifest.workflow_table
      await showTable('workflow-table', workflowRows)
    } else {
      host('workflow-table-title').textContent = 'This workflow has no resource table'
    }
    host('source').textContent = await readStore(
      `${directory}/${manifest.workflow_source}`,
      'text'
    ) ?? ''
  }

  return {
    clear,
    destroy,
    redraw: () => tables.forEach(table => table.redraw(true)),
    renderRun
  }
}
