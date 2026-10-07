import { defineConfig } from 'vite'
import { resolve } from 'node:path'

export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    manifest: true,
    assetsInlineLimit: 0,
    rolldownOptions: {
      input: {
        corpus: resolve(import.meta.dirname, 'corpus/index.html'),
        fixture: resolve(import.meta.dirname, 'fixture/index.html')
      }
    }
  },
  server: {
    proxy: {
      '/corpus/api': { target: 'http://127.0.0.1:8766', rewrite: path => path.replace(/^\/corpus/, '') },
      '/corpus/data': { target: 'http://127.0.0.1:8766', rewrite: path => path.replace(/^\/corpus/, '') },
      '/fixture/data': { target: 'http://127.0.0.1:8765', rewrite: path => path.replace(/^\/fixture/, '') }
    }
  }
})
