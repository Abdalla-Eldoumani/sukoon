import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = 'http://127.0.0.1:8417'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The backend refuses foreign hosts and origins, and the dev server is both.
      '/api': { target: backend, changeOrigin: true, headers: { origin: backend } },
    },
  },
  build: { outDir: 'dist', assetsInlineLimit: 0 },
  test: {
    environment: 'jsdom',
    setupFiles: ['test/setup.ts'],
  },
})
