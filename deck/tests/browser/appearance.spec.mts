// Logic only: a saved preference (Estilo, tema) survives reload and a change of route. The form, saving,
// profiles and permissions live in the React tests with fake ports; how the Deck looks is deliberately
// not asserted here.
import { expect, test } from '@playwright/test';
import { login } from './support/login.mts';
import { savedPreferences, resetAppearanceAfterTest } from './support/appearance.mts';

resetAppearanceAfterTest();

test('el Estilo y el tema guardados sobreviven a recargar y a cambiar de ruta', async ({ page }) => {
  await login(page);
  await savedPreferences(page, { layout: 'operation', theme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-layout', 'operation');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.goto('/soul');
  await expect(page.locator('html')).toHaveAttribute('data-layout', 'operation');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-layout', 'operation');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.goto('/appearance');
  await page.getByRole('region', { name: 'Personalización' }).getByRole('radio', { name: /Equilibrado/ }).check();
  await expect(page.locator('html')).toHaveAttribute('data-layout', 'balanced');
});
