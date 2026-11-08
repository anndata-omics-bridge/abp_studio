// The API console demo: JavaScript run against apb-catalog-ts and the loaded bundle, in a session
// whose variables last from one run to the next, as in a REPL. Pure but for running the code it is
// given: no DOM.

import { javascriptParser, type SyntaxNode } from '../../shared/javascript-parser.js'
import type { Row, Value } from '../types.js'

/** What a run gave: the value its code returned, the lines it printed, or the error it threw. */
export interface Outcome { value: unknown; printed: string[]; error: string | null }

/** One change to code: the text from `from` to `to` replaced by `insert`. */
interface Edit { from: number; to: number; insert: string }

// Nodes that open a scope of their own: names defined inside them are not the session's.
const SCOPES = new Set(['ArrowFunction', 'FunctionExpression', 'ClassExpression'])

/** Code with its top-level declarations turned into assignments, so the names land in the session,
 * and its last expression returned, so its value shows without `return`; with every name it
 * declares. Nested code is left alone. Code that does not parse comes back unchanged, so running
 * it reports the engine's own SyntaxError. */
export function prepare (code: string): { code: string; names: string[] } {
  const tree = javascriptParser.parse(code)
  let broken = false
  tree.iterate({ enter: node => { if (node.type.isError) broken = true; return !broken } })
  if (broken) return { code, names: [] }
  const text = (node: SyntaxNode): string => code.slice(node.from, node.to)
  const edits: Edit[] = []
  const hoisted: string[] = []
  const names: string[] = []
  const define = (node: SyntaxNode): void => {
    if (node.name === 'VariableDefinition') names.push(text(node))
    else if (!SCOPES.has(node.name)) for (let child = node.firstChild; child !== null; child = child.nextSibling) define(child)
  }
  let last: SyntaxNode | null = null
  for (let node = tree.topNode.firstChild; node !== null; node = node.nextSibling) {
    if (node.type.isSkipped) continue
    last = node
    if (node.name === 'VariableDeclaration') {
      const keyword = node.firstChild
      if (keyword === null) continue
      const parts: SyntaxNode[] = []
      for (let child = keyword.nextSibling; child !== null; child = child.nextSibling) if (child.name !== ';') parts.push(child)
      const first = parts[0]
      const end = parts.at(-1)?.to ?? keyword.to
      edits.push({ from: keyword.from, to: keyword.to, insert: first?.name === 'ObjectPattern' ? ';(' : first?.name === 'ArrayPattern' ? ';' : '' })
      for (const [index, part] of parts.entries()) {
        if (!['VariableDefinition', 'ObjectPattern', 'ArrayPattern'].includes(part.name)) continue
        define(part)
        if (parts[index + 1]?.name !== 'Equals') edits.push({ from: part.to, to: part.to, insert: ' = undefined' })
      }
      if (first?.name === 'ObjectPattern') edits.push({ from: end, to: end, insert: ')' })
    } else if (node.name === 'FunctionDeclaration' || node.name === 'ClassDeclaration') {
      const name = node.getChild('VariableDefinition')
      if (name === null) continue
      names.push(text(name))
      if (node.name === 'FunctionDeclaration') {
        hoisted.push(`${text(name)} = ${text(node)};\n`)
        edits.push({ from: node.from, to: node.to, insert: '' })
      } else {
        edits.push({ from: node.from, to: node.from, insert: `${text(name)} = ` })
      }
    }
  }
  const expression = last?.name === 'ExpressionStatement' ? last.firstChild : null
  if (expression !== null) edits.push({ from: expression.from, to: expression.from, insert: 'return (' }, { from: expression.to, to: expression.to, insert: ')' })
  edits.sort((one, other) => one.from - other.from)
  let rewritten = hoisted.join('')
  let at = 0
  for (const edit of edits) {
    rewritten += code.slice(at, edit.from) + edit.insert
    at = edit.to
  }
  return { code: rewritten + code.slice(at), names: [...new Set(names)] }
}

type Run = (this: Record<string, unknown>) => Promise<unknown>
const AsyncFunction = Object.getPrototypeOf(async () => undefined).constructor as new (body: string) => Run

/** Code run with the session's names in scope: `with` makes every name the session holds a live
 * variable, so a function defined in one run sees what a later run assigns. */
function compile (body: string): Run {
  return new AsyncFunction(`with (this) {\n${body}\n}`)
}

// Names every run sets afresh, which are neither the API's nor the user's.
const RUN_NAMES = new Set(['print', 'console'])

/** A REPL session: the API's names plus every name the user's code declares, kept from one run to
 * the next until `reset`. */
export class Session {
  readonly #api: Record<string, unknown>
  #values: Record<string, unknown> = Object.create(null) as Record<string, unknown>

  constructor (api: Record<string, unknown>) {
    this.#api = api
    this.reset()
  }

  /** Forget the user's names: the session holds the API's alone. */
  reset (): void {
    this.#values = Object.assign(Object.create(null) as Record<string, unknown>, this.#api)
  }

  /** The names the user's code has declared or assigned, in the order they came. */
  names (): string[] {
    return Object.keys(this.#values).filter(name => !(name in this.#api) && !RUN_NAMES.has(name))
  }

  /** Run code: an expression shows its value; statements show their last expression's value or
   * what their own `return` gives. `print` and `console.log` collect lines. */
  async run (code: string): Promise<Outcome> {
    const printed: string[] = []
    const print = (...values: unknown[]): void => { printed.push(values.map(value => typeof value === 'string' ? value : shown(value)).join(' ')) }
    const values = this.#values
    values.print = print
    values.console = { log: print, info: print, warn: print, error: print }
    try {
      return { value: await this.#compile(code).call(values), printed, error: null }
    } catch (error) {
      return { value: undefined, printed, error: error instanceof Error ? `${error.name}: ${error.message}` : String(error) }
    }
  }

  // Code that declares nothing is first tried as one expression, so `{ a: 1 }` is an object and not
  // a block; otherwise its declared names join the session before the prepared code runs, so the
  // assignments land there and not on the page.
  #compile (code: string): Run {
    const prepared = prepare(code)
    if (prepared.names.length === 0) {
      try {
        return compile(`return (${code}\n)`)
      } catch {
        // Not one expression: statements, run as prepared below.
      }
    }
    for (const name of prepared.names) if (!(name in this.#values)) this.#values[name] = undefined
    return compile(prepared.code)
  }
}

function isPlain (value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const prototype: unknown = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

/** A value made fit for JSON: a Map as an object, a Set as an array, an error by name and message,
 * a function by name, a class instance as its own fields under its class name; a value met again
 * inside itself as `[circular]`. */
export function plain (value: unknown, seen = new WeakSet<object>()): unknown {
  if (typeof value === 'function') return `[function ${value.name || 'anonymous'}]`
  if (typeof value === 'bigint') return value.toString()
  if (typeof value !== 'object' || value === null) return value
  if (seen.has(value)) return '[circular]'
  seen.add(value)
  if (value instanceof Error) return { error: value.name, message: value.message }
  if (ArrayBuffer.isView(value) && !(value instanceof DataView)) return Array.from(value as unknown as ArrayLike<number>)
  if (value instanceof Map) return Object.fromEntries([...value].map(([key, item]) => [String(key), plain(item, seen)]))
  if (value instanceof Set || Array.isArray(value)) return [...value].map(item => plain(item, seen))
  const fields = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, plain(item, seen)]))
  return isPlain(value) ? fields : { [`(${value.constructor.name})`]: fields }
}

/** A value as indented JSON text. */
export function shown (value: unknown): string {
  return value === undefined ? 'undefined' : JSON.stringify(plain(value), null, 2)
}

/** The rows of a value that reads as a table: a non-empty array of plain objects, or a Map of
 * equal-length columns by name, as `var()` and `select` give; null otherwise. */
export function asRows (value: unknown): Row[] | null {
  if (value instanceof Map) return columnRows(value)
  if (!Array.isArray(value) || value.length === 0 || !value.every(isPlain)) return null
  return value.map(row => plain(row) as Row)
}

/** Columns by name as rows, one per value, a column per name; null unless every entry is a
 * column of one non-zero length. */
function columnRows (columns: Map<unknown, unknown>): Row[] | null {
  const fields: Array<[string, ArrayLike<unknown>]> = []
  for (const [name, values] of columns) {
    if (typeof name !== 'string' || !(Array.isArray(values) || ArrayBuffer.isView(values))) return null
    fields.push([name, values as unknown as ArrayLike<unknown>])
  }
  const length = fields[0]?.[1].length ?? 0
  if (length === 0 || fields.some(([, values]) => values.length !== length)) return null
  return Array.from({ length }, (_, row) => Object.fromEntries(fields.map(([name, values]) => [name, plain(values[row]) as Value])))
}

/** A layer as DataCatalog reads it: its runs, its features, and one array of values per run. */
interface LayerValues { runs: string[]; features: string[]; values: ArrayLike<number | null>[] }

/** A layer as rows, one per feature, a column per run; null for no layer. */
export function layerTable (layer: LayerValues | null, feature = 'feature'): Row[] | null {
  if (layer === null) return null
  return layer.features.map((name, index) => Object.fromEntries([
    [feature, name],
    ...layer.runs.map((run, at) => [run, layer.values[at]?.[index] ?? null])
  ]) as Row)
}

/** Ready-made snippets, each a question the API answers. */
export const EXAMPLES: Array<{ category: string; label: string; code: string }> = [
  {
    category: 'Data', label: 'DIA-NN: the whole var table of a converted result',
    code: `// Read a converted DIA-NN 2.x result, as R's read_parsed_levels does.
const diann = await read_parsed_levels(result('diann_v2-peptidoform_ion'))
// Its ion level's whole var table: every column, the vendor's own included.
diann.levels.get('peptidoform_ion').var()
// diann stays defined: try diann.levels.get('peptidoform_ion').obs() in the console line below.`
  },
  {
    category: 'Data', label: 'DIA-NN: the intensity layer, found by term',
    code: `const diann = await read_parsed_levels(result('diann_v2-peptidoform_ion'))
// Wrap the result in a catalog: the abundance set names its fields.
const catalog = new DataCatalog(bundle, diann, ['abundance_alpha'])
// The term intensity on ions: the catalog finds DIA-NN's column for it and reads it.
const intensity = await catalog.levels.get('peptidoform_ion').layers.get('intensity')
// One row per ion, one column per run.
layerTable(intensity)`
  },
  {
    category: 'Data', label: 'MaxQuant: the same, on a converted MaxQuant result',
    code: `// The same code on a MaxQuant result: the term stays intensity, the column is MaxQuant's.
const maxquant = await read_parsed_levels(result('maxquant_wide-peptidoform_ion'))
const catalog = new DataCatalog(bundle, maxquant, ['abundance_alpha'])
const intensity = await catalog.levels.get('peptidoform_ion').layers.get('intensity')
layerTable(intensity)`
  },
  {
    category: 'Data', label: 'The converted results, and one of them read',
    code: `// results: the names of the converted APB results served with this page (synthetic data),
// each <software>_<version>-<level>. result(name) gives the address read_parsed_levels reads.
return results

// To read one: select the lines below and press ⌘/Ctrl+Enter; only the selection runs.
// The name's last part is its level: diann_v1_7-peptidoform_fragment holds peptidoform_fragment.
const fragments = await read_parsed_levels(result('diann_v1_7-peptidoform_fragment'))
// Its whole var table: every column, the vendor's own included.
fragments.levels.get('peptidoform_fragment').var()`
  },
  { category: 'Sets', label: 'The catalogue sets', code: '// Every set the bundle holds, with its prefix and what it is for.\ncatalogues(bundle)' },
  {
    category: 'Lookup', label: 'What DIA-NN 2.2 calls each abundance term on ions',
    code: `// No data needed: a Catalog answers from the rules alone, by software, version and set.
const ion = new Catalog(bundle, 'DIA-NN', '2.2.0', 'abundance_alpha').levels.get('peptidoform_ion')
// The terms the ion level answers, and the column behind two of them.
return {
  keys: ion.layers.keys(),
  intensity: ion.layers.get('intensity'),
  intensity_norm_settings: ion.layers.get('intensity_norm_settings')
}`
  },
  {
    category: 'Lookup', label: 'DIA-NN 1.8 protein: its intensity layer and q-value column',
    code: `// Python: Catalog("DIA-NN", "1.8.1", "abundance_alpha").levels["protein"].layers["intensity"]
// TypeScript reads [...] as get(...): it gives null where Python raises KeyError; name(...) raises.
const abundance = new Catalog(bundle, 'DIA-NN', '1.8.1', 'abundance_alpha').levels.get('protein')
// q_value is a confidence term, and a Catalog reads one set: ask the confidence set for it.
const confidence = new Catalog(bundle, 'DIA-NN', '1.8.1', 'confidence_alpha').levels.get('protein')
return {
  intensity: abundance.layers.get('intensity'),          // layers['intensity']
  q_value: confidence.var.get('q_value'),                // var['q_value']: one per protein group
  q_value_per_run: confidence.layers.get('q_value')      // layers['q_value']: one per run
}`
  },
  {
    category: 'Lookup', label: 'DIA-NN protein terms, 1.8 and 2.2 side by side',
    code: `// One row per version. DIA-NN 2.x reports no unnormalized protein intensity, only MaxLFQ.
['1.8.1', '2.2.0'].map(version => {
  const abundance = new Catalog(bundle, 'DIA-NN', version, 'abundance_alpha').levels.get('protein')
  const confidence = new Catalog(bundle, 'DIA-NN', version, 'confidence_alpha').levels.get('protein')
  return {
    version,
    intensity: abundance.layers.get('intensity'),
    maxlfq: abundance.layers.get('intensity_norm_settings', { aggregation: 'maxlfq' }),
    q_value: confidence.var.get('q_value'),
    q_value_per_run: confidence.layers.get('q_value')
  }
})`
  },
  {
    category: 'Lookup', label: 'A qualifier picks one of two fields of a term',
    code: `const protein = new Catalog(bundle, 'DIA-NN', '1.8.1', 'abundance_alpha').levels.get('protein').layers
// Two DIA-NN columns are intensity_norm_settings, so the term alone throws and names both.
try { protein.name('intensity_norm_settings') } catch (error) { print(error.message) }
// The aggregation qualifier picks one of them.
return {
  maxlfq: protein.name('intensity_norm_settings', { aggregation: 'maxlfq' }),
  top_n: protein.name('intensity_norm_settings', { aggregation: 'top_n' })
}`
  },
  { category: 'Fields', label: 'Every field MaxQuant 2.0 writes, by term', code: "// One row per MaxQuant 2.0 field the abundance set maps, with its term.\nnew Catalog(bundle, 'MaxQuant', '2.0.1', 'abundance_alpha').fields()" },
  { category: 'Coverage', label: 'What each software version lacks', code: "// The software versions missing a required or recommended abundance term.\nrule_coverage(bundle, 'abundance_alpha').filter(row => row.verdict !== 'pass')" },
  { category: 'Tables', label: 'One set as the long table', code: "// The chromatography set as one table: a row per field and qualifier.\ncatalogue_table(bundle, 'chromatography_alpha')" },
  { category: 'Editor', label: 'The editor\'s tables: their states and problems', code: '// What the Editor tab holds now: each table\'s state, then its problems.\nprint(editor.states())\neditor.problems()' }
]
