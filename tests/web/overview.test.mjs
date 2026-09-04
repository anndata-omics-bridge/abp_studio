import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  DEFAULT_GROUP,
  GROUPS,
  countsBy,
  groupFor,
  overviewViews
} from '../../src/apb_studio/fixture_viewer/web/panels/overview.js'

const ROWS = [
  { module: 'dda_astral', software_name: 'MaxQuant', status: 'ok', downloaded_on: '2026-09-04' },
  { module: 'dda_astral', software_name: 'MaxQuant', status: 'not downloaded', downloaded_on: '' },
  { module: 'dda_astral', software_name: 'Sage', status: 'ok', downloaded_on: '2026-09-03' },
  { module: 'dia_aif', software_name: '', status: 'not_on_server', downloaded_on: '' }
]

test('counts split catalogued from downloaded, smallest group first', () => {
  assert.deepEqual(countsBy(ROWS, 'software_name'), [
    { label: 'Sage', total: 1, downloaded: 1 },
    { label: 'unknown', total: 1, downloaded: 0 },
    { label: 'MaxQuant', total: 2, downloaded: 1 }
  ])
  assert.deepEqual(countsBy(ROWS, 'module'), [
    { label: 'dia_aif', total: 1, downloaded: 0 },
    { label: 'dda_astral', total: 3, downloaded: 2 }
  ])
  assert.deepEqual(countsBy([], 'module'), [], 'an empty store draws nothing')
})

test('dates group by day, oldest first, not by size', () => {
  assert.deepEqual(countsBy(ROWS, 'downloaded_on'), [
    { label: '2026-09-03', total: 1, downloaded: 1 },
    { label: '2026-09-04', total: 1, downloaded: 1 },
    { label: 'unknown', total: 2, downloaded: 0 }
  ])
})

test('the grouping column is whichever offered field is asked for', () => {
  assert.equal(groupFor('module').label, 'Module')
  assert.equal(groupFor('nonsense').field, DEFAULT_GROUP, 'an unknown field falls back')
  assert.equal(groupFor(undefined).field, DEFAULT_GROUP)
  assert.ok(GROUPS.every((group) => group.field && group.label))
})

test('the chart stacks downloaded under pending, per group', () => {
  const [view] = overviewViews(ROWS, 'module')
  assert.equal(view.backend, 'chart')
  assert.match(view.title, /per module \(2\)/)
  const [onDisk, pending] = view.traces
  assert.deepEqual(onDisk.y, ['dia_aif', 'dda_astral'])
  assert.deepEqual(onDisk.x, [0, 2])
  assert.deepEqual(pending.x, [1, 1], 'the bar stays the catalogue count')
  assert.equal(view.layout.barmode, 'stack')

  const [byDefault] = overviewViews(ROWS)
  assert.match(byDefault.title, /per software/)
})
