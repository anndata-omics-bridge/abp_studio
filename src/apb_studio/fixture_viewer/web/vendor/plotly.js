// The chart renderer, pinned in one place.
//
// The full minified distribution at the version rawDIAGQC pins: the 2.x `+esm`
// bundles jsDelivr builds do not parse in the browser, and this one does.
//
// Plotly appends its own rules to document.head for `.js-plotly-plot`, and they do
// not cross a shadow boundary. That is why every panel host renders into the light
// DOM; see shell/fixture-app.js.
export { default as Plotly } from 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.0.0/+esm'
