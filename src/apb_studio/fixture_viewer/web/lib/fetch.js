import { csvParse } from '../vendor/d3-dsv.js'

// Reading store files. A table that has not been written yet is an empty table,
// not an error: the viewer shows what the scripts have produced so far.

/**
 * Fetch one URL, treating 404 as absent.
 *
 * @param {string} url Absolute URL.
 * @returns {Promise<Response|null>} The response, or null when the file is absent.
 */
async function get (url) {
  const response = await fetch(url, { cache: 'no-cache' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return response
}

/**
 * Fetch and parse one CSV file.
 *
 * @param {string} url Absolute URL.
 * @returns {Promise<object[]>} Rows as string-valued objects, empty when absent.
 */
export async function fetchCsv (url) {
  const response = await get(url)
  return response ? csvParse(await response.text()) : []
}

/**
 * Fetch and parse one JSON document.
 *
 * @param {string} url Absolute URL.
 * @returns {Promise<object|null>} The document, or null when absent.
 */
export async function fetchJson (url) {
  const response = await get(url)
  return response ? response.json() : null
}

/**
 * Fetch one text file.
 *
 * @param {string} url Absolute URL.
 * @returns {Promise<string>} The text, empty when absent.
 */
export async function fetchText (url) {
  const response = await get(url)
  return response ? response.text() : ''
}
