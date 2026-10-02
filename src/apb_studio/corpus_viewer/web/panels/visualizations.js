import { node } from '../render/dom.js'
import { renderScalePlot, resizeScalePlot } from '../render/plotly.js'
import { timingFacetFigure } from '../render/timing-facets.js'
import { xAxisChoices, xLabel, xValue } from '../render/x-axis.js'

// Resource-profile panel. It owns only its selected workflow/step tab and Plotly mounts.

function chartLayout (xTitle, yTitle, hasData) {
  return {
    height: 400,
    margin: { l: 80, r: 16, t: 12, b: 110 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 },
    legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.34 },
    xaxis: { title: { text: xTitle }, automargin: true, zeroline: false },
    yaxis: { title: { text: yTitle }, automargin: true, zeroline: false },
    annotations: hasData
      ? []
      : [{
          text: 'No persisted measurements are available for this chart.',
          showarrow: false,
          x: 0.5,
          y: 0.5,
          xref: 'paper',
          yref: 'paper'
        }]
  }
}

function traceSeries (points, stepSeries) {
  const software = [...new Set(points.map(point => point.software_name))].sort()
  if (!stepSeries) return software.map(name => ({ name, step: '', software: name }))
  const steps = [...new Set(points.map(point => point.step))]
  return steps.flatMap(step => software.map(name => ({
    name: `${step} · ${name}`,
    step,
    software: name
  })))
}

function tracesFor (
  points,
  yField,
  yLabel,
  { artifact = false, stepSeries = false, xAxis = 'input_size_mib' } = {}
) {
  return traceSeries(points, stepSeries).map(series => {
    const selected = points.filter(point =>
      point.software_name === series.software &&
      (!series.step || point.step === series.step) &&
      xValue(point, xAxis) != null &&
      point[yField] != null
    )
    return {
      type: 'scatter',
      mode: 'markers',
      name: series.name,
      x: selected.map(point => xValue(point, xAxis)),
      y: selected.map(point => point[yField]),
      text: selected.map(point => point.input_file),
      customdata: selected.map(point => [
        point.module,
        point.software_name,
        point.step,
        point.tool,
        point.status,
        artifact ? point.output_role : '',
        artifact ? point.output_path : ''
      ]),
      marker: { size: 8, opacity: 0.78 },
      hovertemplate: `<b>%{text}</b><br>module=%{customdata[0]}<br>software=%{customdata[1]}<br>step=%{customdata[2]}<br>tool=%{customdata[3]}<br>status=%{customdata[4]}${artifact ? '<br>output role=%{customdata[5]}<br>output=%{customdata[6]}' : ''}<br>${xLabel(xAxis)}=%{x:${xAxis === 'input_size_mib' ? '.2f' : ',.0f'}}<br>${yLabel}=%{y:.2f}<extra>%{fullData.name}</extra>`
    }
  }).filter(trace => trace.x.length)
}

function chartsFor (view, timingView = null, xAxis = 'input_size_mib') {
  const axisLabel = xLabel(xAxis)
  if (timingView) {
    return [{
      key: 'tool-timings',
      title: `${timingView.label} phases by ${axisLabel.toLowerCase()}`,
      points: timingView.points,
      faceted: true
    }]
  }
  const workflow = view.key === 'workflow'
  return [
    {
      key: 'runtime',
      title: workflow
        ? `Total workflow runtime by ${axisLabel.toLowerCase()}`
        : `Step runtime by ${axisLabel.toLowerCase()}`,
      points: view.steps,
      field: 'runtime_seconds',
      x: axisLabel,
      y: workflow ? 'Total workflow runtime (seconds)' : 'Step runtime (seconds)',
      label: 'runtime (seconds)'
    },
    {
      key: 'memory',
      title: workflow
        ? `Maximum workflow memory by ${axisLabel.toLowerCase()}`
        : `Step peak memory by ${axisLabel.toLowerCase()}`,
      points: view.steps,
      field: 'peak_memory_mib',
      x: axisLabel,
      y: workflow ? 'Maximum step peak RSS (MiB)' : 'Peak process-tree RSS (MiB)',
      label: 'peak RSS (MiB)'
    },
    {
      key: 'output',
      title: workflow
        ? `Artifact size after each step by ${axisLabel.toLowerCase()}`
        : `Generated artifact size by ${axisLabel.toLowerCase()}`,
      points: view.outputs,
      field: 'output_size_mib',
      x: axisLabel,
      y: 'Generated artifact size (MiB)',
      label: 'output size (MiB)',
      artifact: true,
      stepSeries: workflow
    }
  ]
}

function mountGrid (host, view, subtab, charts, xAxis) {
  const signature = JSON.stringify([view.key, subtab, xAxis, charts.map(chart => chart.key)])
  if (host.dataset.view === signature) return
  const grid = document.createElement('div')
  grid.className = 'chart-grid'
  for (const chart of charts) {
    const section = document.createElement('section')
    section.className = 'view chart-view'
    const chartHost = document.createElement('div')
    chartHost.className = 'chart'
    chartHost.dataset.chart = chart.key
    section.append(node('h3', chart.title), chartHost)
    grid.append(section)
  }
  host.replaceChildren(grid)
  host.dataset.view = signature
}

/** Build the stateful visualization panel around its two shell hosts. */
export function createVisualizationPanel (tabs, panel) {
  let selectedKey = 'workflow'
  let views = []
  const selectedSubtabs = new Map()
  const axisSelect = tabs.parentElement.querySelector('#visualization-x-axis')
  axisSelect.addEventListener('change', () => { void activate() })

  function timingContent (view) {
    const timingViews = view.timingViews ?? []
    if (!timingViews.length) {
      if (panel.dataset.subtabs) {
        panel.replaceChildren()
        delete panel.dataset.subtabs
        delete panel.dataset.view
      }
      return { host: panel, timingView: null, subtab: 'studio' }
    }
    const signature = JSON.stringify([view.key, timingViews.map(timing => [timing.key, timing.label])])
    if (panel.dataset.subtabs !== signature) {
      const navigation = document.createElement('nav')
      navigation.className = 'tabs subtabs tool-timing-tabs'
      navigation.setAttribute('role', 'tablist')
      navigation.setAttribute('aria-label', `Timing views for ${view.label}`)
      const content = document.createElement('section')
      content.id = 'tool-timing-content'
      content.className = 'tool-timing-content'
      content.setAttribute('role', 'tabpanel')
      const subtabs = [{ key: 'studio', label: 'Studio timings' }, ...timingViews]
      for (const [index, subtab] of subtabs.entries()) {
        const button = document.createElement('button')
        button.type = 'button'
        button.id = `tool-timing-tab-${index}`
        button.textContent = subtab.label
        button.dataset.timingTab = subtab.key
        button.setAttribute('role', 'tab')
        button.setAttribute('aria-controls', content.id)
        button.addEventListener('click', () => {
          selectedSubtabs.set(view.key, subtab.key)
          void activate()
        })
        button.addEventListener('keydown', event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
          const target = event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? subtabs.length - 1
              : (index + (event.key === 'ArrowRight' ? 1 : -1) + subtabs.length) % subtabs.length
          event.preventDefault()
          navigation.children[target].focus()
          navigation.children[target].click()
        })
        navigation.append(button)
      }
      panel.replaceChildren(navigation, content)
      panel.dataset.subtabs = signature
      delete panel.dataset.view
    }
    const key = selectedSubtabs.get(view.key) ?? 'studio'
    const timingView = timingViews.find(timing => timing.key === key) ?? null
    const selected = timingView?.key ?? 'studio'
    selectedSubtabs.set(view.key, selected)
    const navigation = panel.querySelector('.tool-timing-tabs')
    const content = panel.querySelector('.tool-timing-content')
    for (const button of navigation.querySelectorAll('[role="tab"]')) {
      const active = button.dataset.timingTab === selected
      button.setAttribute('aria-selected', String(active))
      button.tabIndex = active ? 0 : -1
      if (active) content.setAttribute('aria-labelledby', button.id)
    }
    return { host: content, timingView, subtab: selected }
  }

  async function activate () {
    const view = views.find(candidate => candidate.key === selectedKey) ?? views[0]
    if (!view) {
      panel.replaceChildren()
      return
    }
    selectedKey = view.key
    for (const button of tabs.querySelectorAll('[role="tab"]')) {
      const selected = button.dataset.visualizationTab === view.key
      button.setAttribute('aria-selected', String(selected))
      button.tabIndex = selected ? 0 : -1
      if (selected) panel.setAttribute('aria-labelledby', button.id)
    }
    panel.setAttribute('aria-busy', 'true')
    const { host, timingView, subtab } = timingContent(view)
    const xAxis = axisSelect.value
    const charts = chartsFor(view, timingView, xAxis)
    mountGrid(host, view, subtab, charts, xAxis)
    try {
      await Promise.all(charts.map(chart => {
        const chartHost = host.querySelector(`[data-chart="${chart.key}"]`)
        const figure = chart.faceted
          ? timingFacetFigure(chart.points, xAxis)
          : null
        const traces = figure?.traces ?? tracesFor(chart.points, chart.field, chart.label, {
          artifact: chart.artifact,
          stepSeries: chart.stepSeries,
          xAxis
        })
        return renderScalePlot(
          chartHost,
          traces,
          figure?.layout ?? chartLayout(chart.x, chart.y, Boolean(traces.length))
        )
      }))
    } finally {
      panel.removeAttribute('aria-busy')
    }
  }

  function rebuildTabs () {
    const signature = JSON.stringify(views.map(view => [view.key, view.label]))
    if (tabs.dataset.views === signature) return
    tabs.dataset.views = signature
    tabs.replaceChildren(...views.map((view, index) => {
      const button = document.createElement('button')
      button.type = 'button'
      button.id = `visualization-tab-${index}`
      button.textContent = view.label
      button.dataset.visualizationTab = view.key
      button.setAttribute('role', 'tab')
      button.setAttribute('aria-controls', panel.id)
      button.setAttribute('aria-selected', 'false')
      button.tabIndex = -1
      button.addEventListener('click', () => {
        selectedKey = view.key
        void activate()
      })
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
        const target = event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? views.length - 1
            : (index + (event.key === 'ArrowRight' ? 1 : -1) + views.length) % views.length
        event.preventDefault()
        const next = tabs.children[target]
        selectedKey = next.dataset.visualizationTab
        next.focus()
        void activate()
      })
      return button
    }))
  }

  function rebuildAxes () {
    const choices = xAxisChoices(views)
    const signature = JSON.stringify(choices)
    if (axisSelect.dataset.choices === signature) return
    const selected = axisSelect.value
    axisSelect.replaceChildren(...choices.map(choice => {
      const option = document.createElement('option')
      option.value = choice.value
      option.textContent = choice.label
      return option
    }))
    axisSelect.value = choices.some(choice => choice.value === selected)
      ? selected
      : 'input_size_mib'
    axisSelect.dataset.choices = signature
  }

  return {
    /** @param {object[]} nextViews Workflow and step chart views. */
    async render (nextViews) {
      views = nextViews
      rebuildAxes()
      if (!views.some(view => view.key === selectedKey)) selectedKey = 'workflow'
      rebuildTabs()
      await activate()
    },

    /** Resize every mounted Plotly chart after revealing its tab. */
    resize () {
      for (const host of panel.querySelectorAll('.chart')) {
        resizeScalePlot(host)
      }
    }
  }
}
