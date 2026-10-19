import { defineConfig, devices } from '@playwright/test'

// Browser tests run against the separate "steady-e2e" Docker stack (port 5174),
// never against your real data on port 5173. Start it with:
//   FRONTEND_PORT=5174 BACKEND_PORT=8001 docker compose -p steady-e2e up -d --build
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5174'
if (new URL(baseURL).port === '5173') {
  throw new Error('Refusing to run browser tests against port 5173 (your real data). Use the steady-e2e stack.')
}

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    { name: 'desktop', use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/state.json' }, dependencies: ['setup'] },
    { name: 'phone', use: { ...devices['Pixel 7'], storageState: 'e2e/.auth/state.json' }, dependencies: ['setup'], grep: /@phone/ },
  ],
})
