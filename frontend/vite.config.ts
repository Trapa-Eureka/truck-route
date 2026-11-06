import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In development the Django API runs on :8000; proxying keeps the browser on a single origin.
export default defineConfig({
  plugins: [react()],
  // maplibre-gl 6 loads its worker relative to its own file. Vite's dev pre-bundling moves the
  // main file into .vite/deps and the worker lookup 404s ("Worker failed to load"), so serve it as-is.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
  test: {
    include: ['src/**/*.test.ts'],
    // Times the user types are local times; fix the zone so the tests do not depend on the machine.
    env: { TZ: 'America/Chicago' },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
