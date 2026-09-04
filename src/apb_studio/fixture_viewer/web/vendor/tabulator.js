// The table renderer, pinned in one place.
//
// TabulatorFull is the build with every module compiled in -- sorting, header
// filters and formatters all work without registering modules by hand.
//
// Its stylesheet is a separate pinned <link> in index.html. Tabulator ships CSS
// rather than inlining it, so an unstyled table is what a missing or misversioned
// stylesheet looks like.
export { TabulatorFull } from 'https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.2/+esm'
