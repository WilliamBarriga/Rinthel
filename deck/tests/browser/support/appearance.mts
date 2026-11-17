import { expect, test, type Page } from '@playwright/test';
import { defaultPreferences } from '../../../shared/appearance.mts';

/** The saved appearance of an account that never touched it: what every spec starts from and restores. */
const DEFAULT_APPEARANCE = { version: 1, preferences: defaultPreferences, profiles: [] };

/** Saves preferences through the API (the controls live in Apariencia) and reloads to apply them. */
export async function savedPreferences(page: Page, patch: Record<string, unknown>) {
  await expect(page.locator('main')).toBeVisible(); // signed in
  const response = await page.request.get('/api/appearance');
  expect(response.ok()).toBe(true);
  const { personal } = await response.json();
  const current = personal ?? DEFAULT_APPEARANCE;
  const saved = await page.request.put('/api/appearance', { data: { ...current, preferences: { ...current.preferences, ...patch } } });
  expect(saved.ok()).toBe(true);
  await page.reload();
}

/** Puts the saved appearance back after every test of the spec that calls it. */
export function resetAppearanceAfterTest() {
  test.afterEach(async ({ page }) => {
    await page.request.put('/api/appearance', { data: DEFAULT_APPEARANCE });
  });
}

export type ThemeChoice = 'Claro' | 'Oscuro' | 'Cyberpunk' | 'Sistema';
/** Picks a theme through the radio group of the Sidebar (the admin's: the theme is the Instance's). */
export async function setTheme(page: Page, theme: ThemeChoice) {
  await page.getByRole('radiogroup', { name: 'Tema' }).getByRole('radio', { name: theme, exact: true }).click();
}
