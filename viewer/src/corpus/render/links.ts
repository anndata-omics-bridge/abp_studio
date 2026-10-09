const BINARY_SUFFIX = /\.(?:h5mu|h5ad|h5|hdf5|duckdb|parquet|arrow|feather|sqlite3?|db|bin|zip|gz|bz2|xz|7z|xlsx?)$/i

/** Open readable files and folders in a tab; download binary files in place. */
export function fileLink (href: string, label: string, { directory = false } = {}): HTMLAnchorElement {
  const link = document.createElement('a')
  const url = new URL(href, document.baseURI)
  const path = decodeURIComponent(url.pathname)
  if (/\.json$/i.test(path)) url.searchParams.delete('view')
  link.href = url.href
  link.textContent = label
  if (!directory && BINARY_SUFFIX.test(path)) {
    link.download = path.split('/').at(-1) ?? ''
  } else {
    link.target = '_blank'
    link.rel = 'noopener noreferrer'
  }
  link.addEventListener('click', event => event.stopPropagation())
  return link
}
