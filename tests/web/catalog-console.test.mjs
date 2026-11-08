import assert from 'node:assert/strict'
import { test } from 'node:test'

import { asRows, layerTable, plain, prepare, Session, shown } from '../../viewer/src/catalog/projections/console.ts'

// One run in a fresh session.
const run = (code, scope) => new Session(scope).run(code)

test('an expression shows its value, statements what they return, with the scope bound by name', async () => {
  assert.deepEqual(await run('answer * 2', { answer: 21 }), { value: 42, printed: [], error: null })
  const outcome = await run('const doubled = answer * 2\nprint("doubled", doubled)\nconsole.log({ doubled })\nreturn doubled', { answer: 21 })
  assert.deepEqual(outcome, { value: 42, printed: ['doubled 42', '{\n  "doubled": 42\n}'], error: null })
})

test('a thrown error comes back as its name and message, with what was printed before it', async () => {
  assert.deepEqual(await run("print('before')\nthrow new RangeError('no such level')", {}), {
    value: undefined,
    printed: ['before'],
    error: 'RangeError: no such level'
  })
  assert.equal((await run('missing', {})).error, 'ReferenceError: missing is not defined')
})

test('a value is made fit for JSON: maps, sets, class instances, functions and cycles', () => {
  class Level { constructor () { this.name = 'protein' } }
  const cycle = { name: 'cycle' }
  cycle.self = cycle
  assert.deepEqual(plain({ map: new Map([['a', 1]]), set: new Set([1, 2]), level: new Level(), act: function act () {}, cycle }), {
    map: { a: 1 },
    set: [1, 2],
    level: { '(Level)': { name: 'protein' } },
    act: '[function act]',
    cycle: { name: 'cycle', self: '[circular]' }
  })
  assert.equal(shown(undefined), 'undefined')
})

test('an array of plain objects reads as rows; anything else does not', () => {
  assert.deepEqual(asRows([{ key: 'intensity' }, { key: 'ibaq' }]), [{ key: 'intensity' }, { key: 'ibaq' }])
  assert.equal(asRows([]), null)
  assert.equal(asRows(['intensity']), null)
  assert.equal(asRows({ key: 'intensity' }), null)
})

test('a layer reads as one row per feature with a column per run; typed arrays read as arrays', () => {
  const layer = { runs: ['S0', 'S1'], features: ['P1', 'P2'], values: [Float64Array.from([1, 2]), Float64Array.from([3, 4])] }
  assert.deepEqual(layerTable(layer, 'protein'), [{ protein: 'P1', S0: 1, S1: 3 }, { protein: 'P2', S0: 2, S1: 4 }])
  assert.equal(layerTable(null), null)
  assert.deepEqual(plain(Float64Array.from([0.5, 1])), [0.5, 1])
})

test('columns by name, as var() and select give, read as one row per value', () => {
  const columns = new Map([['ProForma_ion', ['PEPTIDE/2', 'PEPTIDEK/3']], ['Charge', Float64Array.from([2, 3])]])
  assert.deepEqual(asRows(columns), [
    { ProForma_ion: 'PEPTIDE/2', Charge: 2 },
    { ProForma_ion: 'PEPTIDEK/3', Charge: 3 }
  ])
  assert.equal(asRows(new Map()), null)
  assert.equal(asRows(new Map([['a', [1]], ['b', [1, 2]]])), null)
  assert.equal(asRows(new Map([['a', 1]])), null)
})

test('a leading comment keeps an expression an expression; code after a return is left unrun', async () => {
  assert.equal((await run('// the answer\nanswer', { answer: 42 })).value, 42)
  const outcome = await run('// first\nreturn answer\n\n// second\nprint("ran")\nreturn 0', { answer: 42 })
  assert.deepEqual(outcome, { value: 42, printed: [], error: null })
})

test('top-level declarations become assignments; the last expression is returned', () => {
  assert.deepEqual(prepare('const a = 1, b'), { code: ' a = 1, b = undefined', names: ['a', 'b'] })
  assert.deepEqual(prepare('const { levels } = diann;'), { code: ';( { levels } = diann);', names: ['levels'] })
  assert.deepEqual(prepare('let [first] = results'), { code: '; [first] = results', names: ['first'] })
  assert.deepEqual(prepare('class K {}'), { code: 'K = class K {}', names: ['K'] })
  assert.deepEqual(prepare('const x = 1\nx + 1;'), { code: ' x = 1\nreturn (x + 1);', names: ['x'] })
  assert.deepEqual(prepare('function f (x) { return x }\nf(1)'), { code: 'f = function f (x) { return x };\n\nreturn (f(1))', names: ['f'] })
})

test('nested code is left alone; names inside a default value are not declared; broken code comes back unchanged', () => {
  assert.deepEqual(prepare('for (const r of results) print(r)'), { code: 'for (const r of results) print(r)', names: [] })
  assert.deepEqual(prepare('function h () { const inner = 1; return inner }').names, ['h'])
  assert.deepEqual(prepare('const { a, b: c = (z) => z } = o').names, ['a', 'c'])
  assert.deepEqual(prepare('const x = ('), { code: 'const x = (', names: [] })
})

test('a session keeps what each run declares, and forgets it on reset', async () => {
  const session = new Session({ answer: 42 })
  assert.deepEqual(await session.run('const x = 1\nfunction twice (n) { return 2 * n }'), { value: undefined, printed: [], error: null })
  assert.equal((await session.run('twice(x) + answer')).value, 44)
  assert.deepEqual(session.names(), ['x', 'twice'])
  session.reset()
  assert.deepEqual(session.names(), [])
  assert.equal((await session.run('x')).error, 'ReferenceError: x is not defined')
  assert.equal((await session.run('answer')).value, 42)
})

test('a function is defined before the code that calls it, and sees later values', async () => {
  const session = new Session({})
  assert.equal((await session.run('const y = double(2)\nfunction double (n) { return n * 2 }\ny')).value, 4)
  await session.run('let n = 1\nfunction current () { return n }')
  await session.run('n = 5')
  assert.equal((await session.run('current()')).value, 5)
})

test('a declared name lands in the session even where the page has it; an error keeps what ran before it', async () => {
  const session = new Session({})
  await session.run("const name = 'mine'")
  assert.equal((await session.run('name')).value, 'mine')
  assert.equal(globalThis.name, undefined)
  assert.equal((await session.run("const kept = 1\nthrow new Error('stop')")).error, 'Error: stop')
  assert.equal((await session.run('kept')).value, 1)
})

test('code declaring nothing is first one expression, so an object literal is an object', async () => {
  assert.deepEqual((await run('{ keys: 1, other: 2 }', {})).value, { keys: 1, other: 2 })
  assert.equal((await run('function f () { return 1 }\nf()', {})).value, 1)
})
