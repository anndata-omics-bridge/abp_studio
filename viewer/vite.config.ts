import { defineConfig, searchForWorkspaceRoot } from 'vite'
import { resolve } from 'node:path'

// apb-catalog-ts is read from its sibling checkout, as tsconfig.json's `paths` declares.
const APB_CATALOG_TS = resolve(import.meta.dirname, '../../apb-catalog-ts')

export default defineConfig({
  base: './',
  resolve: {
    alias: { '@anndata-omics-bridge/apb-catalog': resolve(APB_CATALOG_TS, 'src/index.ts') }
  },
  build: {
    outDir: 'dist',
    manifest: true,
    assetsInlineLimit: 0,
    rolldownOptions: {
      input: {
        catalog: resolve(import.meta.dirname, 'catalog/index.html'),
        corpus: resolve(import.meta.dirname, 'corpus/index.html'),
        fixture: resolve(import.meta.dirname, 'fixture/index.html')
      }
    }
  },
  server: {
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), APB_CATALOG_TS] },
    proxy: {
      '/catalog/data': { target: 'http://127.0.0.1:8767', rewrite: path => path.replace(/^\/catalog/, '') },
      '/corpus/data': { target: 'http://127.0.0.1:8766', rewrite: path => path.replace(/^\/corpus/, '') },
      '/fixture/data': { target: 'http://127.0.0.1:8765', rewrite: path => path.replace(/^\/fixture/, '') }
    }
  }
})
