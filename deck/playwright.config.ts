import { defineConfig } from '@playwright/test';
// The specs run the real web app against `tests/browser/support/fake-deck.mts`: the real Deck routers
// over a fake daemon and an in-memory store, so nothing is started by hand and no key is needed.
// The ports are picked once, here, and handed down through the environment so the main process and
// every worker agree on them; `DECK_E2E_API_PORT` / `DECK_E2E_WEB_PORT` pin them. No server is
// reused: a stale one on the same port would answer for the new run.
const pick = () => 20000 + Math.floor(Math.random() * 20000);
const API_PORT = (process.env.DECK_E2E_API_PORT ||= String(pick()));
const WEB_PORT = (process.env.DECK_E2E_WEB_PORT ||= String(pick()));
const FAKE_DECK = `http://127.0.0.1:${API_PORT}`;
export default defineConfig({
  testDir: './tests/browser', testMatch: '**/*.spec.mts', timeout: 45000, workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`, browserName: 'chromium', headless: true,
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } } : {}),
  },
  webServer: [
    { command: 'node --import tsx tests/browser/support/fake-deck.mts', url: `${FAKE_DECK}/api/auth/status`, env: { FAKE_DECK_PORT: API_PORT }, reuseExistingServer: false },
    { command: `npm run dev -w @deck/web -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`, url: `http://127.0.0.1:${WEB_PORT}`, env: { DECK_API_URL: FAKE_DECK }, reuseExistingServer: false },
  ],
});
