// One shared software legend and one independently scaled panel per tool phase.
import { xLabel, xValue } from './x-axis.js'

const SOFTWARE_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
  '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#393b79', '#637939',
  '#8c6d31', '#843c39', '#7b4173', '#3182bd'
]

function axisName (prefix, index) {
  return index === 0 ? prefix : `${prefix}${index + 1}`
}

/** Project tool timing points into vertically faceted Plotly traces and layout. */
export function timingFacetFigure (points, xAxis = 'input_size_mib') {
  const phases = [...new Set(points.map(point => point.phase))]
  const software = [...new Set(points.map(point => point.software_name))].sort()
  const traces = []
  const shownInLegend = new Set()

  for (const [phaseIndex, phase] of phases.entries()) {
    for (const [softwareIndex, name] of software.entries()) {
      const selected = points.filter(point =>
        point.phase === phase && point.software_name === name &&
        xValue(point, xAxis) != null && point.duration_seconds != null
      )
      if (!selected.length) continue
      traces.push({
        type: 'scatter',
        mode: 'markers',
        name,
        legendgroup: name,
        showlegend: !shownInLegend.has(name),
        xaxis: axisName('x', phaseIndex),
        yaxis: axisName('y', phaseIndex),
        x: selected.map(point => xValue(point, xAxis)),
        y: selected.map(point => point.duration_seconds),
        text: selected.map(point => point.input_file),
        customdata: selected.map(point => [
          point.module, point.step, point.tool, point.status,
          point.timing_path, point.phase
        ]),
        marker: {
          size: 8,
          opacity: 0.78,
          color: SOFTWARE_COLORS[softwareIndex % SOFTWARE_COLORS.length]
        },
        hovertemplate: '<b>%{text}</b><br>software=%{fullData.name}' +
          '<br>module=%{customdata[0]}<br>step=%{customdata[1]}' +
          '<br>tool=%{customdata[2]}<br>status=%{customdata[3]}' +
          '<br>phase=%{customdata[5]}<br>timing file=%{customdata[4]}' +
          `<br>${xLabel(xAxis)}=%{x:${xAxis === 'input_size_mib' ? '.2f' : ',.0f'}}` +
          '<br>duration=%{y:.3f} seconds<extra></extra>'
      })
      shownInLegend.add(name)
    }
  }

  const gap = phases.length > 1 ? 0.07 : 0
  const panelHeight = phases.length ? (1 - gap * (phases.length - 1)) / phases.length : 1
  const layout = {
    height: Math.max(440, phases.length * 260 + 150),
    margin: { l: 80, r: 16, t: 35, b: 145 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 11 },
    legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.13, groupclick: 'togglegroup' },
    annotations: phases.map((phase, index) => ({
      text: phase,
      x: 0,
      y: 1 - index * (panelHeight + gap) + 0.02,
      xref: 'paper',
      yref: 'paper',
      xanchor: 'left',
      showarrow: false,
      font: { size: 13, color: '#263442' }
    }))
  }
  for (const index of phases.keys()) {
    const xaxis = axisName('xaxis', index)
    const yaxis = axisName('yaxis', index)
    const x = axisName('x', index)
    const y = axisName('y', index)
    const top = 1 - index * (panelHeight + gap)
    layout[xaxis] = {
      anchor: y,
      matches: index === 0 ? undefined : 'x',
      showticklabels: index === phases.length - 1,
      title: index === phases.length - 1 ? { text: xLabel(xAxis) } : undefined,
      zeroline: false
    }
    layout[yaxis] = {
      anchor: x,
      domain: [top - panelHeight, top],
      title: { text: 'Seconds' },
      automargin: true,
      zeroline: false,
      rangemode: 'tozero'
    }
  }
  return { traces, layout, phases }
}
