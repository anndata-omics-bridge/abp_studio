import { fileUrl, readStore, sourceUrl } from '../lib/fetch.js'
import { renderJson } from '../render/dom.js'
import { fileLink } from '../render/links.js'
import { mountTable } from '../render/tabulator.js'

const tableOptions = {
  height: '55vh',
  placeholder: 'No records',
  columnDefaults: { formatter: 'plaintext', headerFilter: 'input' }
}

function columnsFor (rows, sourceDirectory = '') {
  return rows.columns.map(field => {
    if (!sourceDirectory || !['input_file', 'vendor_parameter_file', 'fasta'].includes(field)) {
      return { title: field, field }
    }
    return {
      title: field,
      field,
      formatter: cell => {
        const path = cell.getValue()
        if (!path) return ''
        return fileLink(sourceUrl(sourceDirectory, path), path)
      }
    }
  })
}

function renderLinks (target, directory, names) {
  const links = [...new Set(names.filter(Boolean))].map(name =>
    fileLink(fileUrl(`${directory}/${name}`), name))
  target.replaceChildren(...links)
}

/** Own the Settings & inputs panel and its Tabulator handles. */
export function createSettingsPanel (app) {
  let tables = []
  const host = id => app.hostFor(id)

  function destroy () {
    for (const table of tables) table.destroy()
    tables = []
  }

  function clear () {
    destroy()
    for (const id of ['links', 'manifest', 'run-manifest', 'corpus', 'input-metadata-table', 'workflow-table', 'source']) {
      host(id).replaceChildren()
    }
    host('corpus-description').textContent = ''
  }

  async function showTable (id, rows, sourceDirectory = '') {
    const table = await mountTable(host(id), rows, columnsFor(rows, sourceDirectory), tableOptions)
    tables.push(table)
  }

  async function renderRun ({ directory, storeRoot, manifest, config, corpus, inputMetadata, workflowRows }) {
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
    renderLinks(host('links'), directory, [
      'run.json',
      manifest.execution_settings,
      manifest.source_corpus,
      manifest.corpus,
      manifest.input_metadata,
      manifest.workflow_table,
      manifest.workflow_source
    ])
    const inventory = await readStore(`${directory}/${manifest.source_corpus}`, 'csv')
    host('corpus-title').textContent = `Corpus: ${config.corpus.split('/').at(-1)}`
    host('corpus-description').textContent =
      `${inventory.length} inventory entries · ${corpus.length} selected for this run. ` +
      'This is the frozen run snapshot.'
    await showTable('corpus', inventory, directory)
    host('input-metadata-table').replaceChildren()
    if (manifest.input_metadata) {
      host('input-metadata-title').textContent = `Input sizes: ${manifest.input_metadata}`
      await showTable('input-metadata-table', inputMetadata, directory)
    } else {
      host('input-metadata-title').textContent = 'No input-size snapshot in this run'
    }
    host('workflow-table').replaceChildren()
    if (manifest.workflow_table) {
      host('workflow-table-title').textContent = manifest.workflow_table
      await showTable('workflow-table', workflowRows, directory)
    } else {
      host('workflow-table-title').textContent = 'This workflow has no resource table'
    }
    host('source').textContent = await readStore(
      `${directory}/${manifest.workflow_source}`,
      'text'
    )
  }

  return {
    clear,
    destroy,
    redraw: () => tables.forEach(table => table.redraw(true)),
    renderRun
  }
}
