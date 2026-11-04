import type { Manifest, RuleDocument, RuleLevel, Value } from './types.js'

// The rules bundle as apb2's `make rules-bundle` writes it, read as files: manifest.json first,
// then rules.json and levels.json; each rules.json verbatim only when the Document view asks.

const BUNDLE_FORMAT = 1

async function json (url: URL): Promise<unknown> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Cannot read ${url.href}: ${response.status} ${response.statusText}`)
  return response.json()
}

function listed<T> (payload: unknown, key: string, file: string): T[] {
  const value = typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>)[key] : undefined
  if (!Array.isArray(value)) throw new Error(`${file} lists no ${key}`)
  return value as T[]
}

export class RulesBundle {
  readonly url: URL
  readonly manifest: Manifest
  readonly rules: RuleDocument[]
  readonly levels: RuleLevel[]
  #documents = new Map<string, Promise<Value>>()

  constructor (url: URL, manifest: Manifest, rules: RuleDocument[], levels: RuleLevel[]) {
    this.url = url
    this.manifest = manifest
    this.rules = rules
    this.levels = levels
  }

  /** Load the bundle whose manifest.json is at `manifestUrl`. */
  static async load (manifestUrl: string): Promise<RulesBundle> {
    const url = new URL(manifestUrl)
    const manifest = await json(url) as Manifest
    if (manifest.bundle_format !== BUNDLE_FORMAT) {
      throw new Error(`Rules bundle format ${String(manifest.bundle_format)}; this viewer reads format ${BUNDLE_FORMAT}: rerun make rules-bundle in apb2`)
    }
    const [rules, levels] = await Promise.all([
      json(new URL('rules.json', url)).then(payload => listed<RuleDocument>(payload, 'rules', 'rules.json')),
      json(new URL('levels.json', url)).then(payload => listed<RuleLevel>(payload, 'levels', 'levels.json'))
    ])
    return new RulesBundle(url, manifest, rules, levels)
  }

  /** One packaged rules.json, as apb2 ships it. */
  document (rule: string): Promise<Value> {
    let document = this.#documents.get(rule)
    if (!document) {
      document = json(new URL(`documents/${rule}`, this.url)) as Promise<Value>
      this.#documents.set(rule, document)
    }
    return document
  }
}
