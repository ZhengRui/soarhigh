import { defineConfig } from '@playwright/test';

// Runs against a dedicated port (not 3000, where a developer's own `bun run
// dev` typically lives) and always starts a fresh server for the checkout
// under test: reusing an already-running server on a shared port risks
// silently testing whatever code that other server happens to be running.
const E2E_PORT = 3100;

export default defineConfig({
  testDir: 'e2e',
  webServer: {
    command: 'bun run dev',
    port: E2E_PORT,
    env: { PORT: String(E2E_PORT) },
    reuseExistingServer: false,
  },
  use: {
    baseURL: `http://localhost:${E2E_PORT}`,
  },
});
