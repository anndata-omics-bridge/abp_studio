import { removeSection, sectionFor, updateSection } from './section.js'

// Preformatted text, for column lists, JSON documents and parameter files.

export const noteRenderer = {
  name: 'note',

  /**
   * Render a text block into a new section of the host.
   *
   * @param {HTMLElement} host The panel host.
   * @param {object} view The view, with `text`.
   * @returns {Promise<object>} The handle for later calls.
   */
  async mount (host, view) {
    const { section, body } = sectionFor(host, view)
    const pre = document.createElement('pre')
    pre.textContent = view.text
    body.append(pre)
    return { section, body, pre, view }
  },

  /**
   * Replace the text.
   *
   * @param {object} handle The handle from `mount`.
   * @param {object} view The new view.
   */
  async update (handle, view) {
    handle.view = view
    updateSection(handle.body, view)
    handle.pre.textContent = view.text
  },

  /** @param {object} _handle Unused; text needs no re-measure. */
  resize (_handle) {},

  /**
   * Remove the block.
   *
   * @param {object} handle The handle from `mount`.
   */
  destroy (handle) {
    removeSection(handle.body)
  }
}
