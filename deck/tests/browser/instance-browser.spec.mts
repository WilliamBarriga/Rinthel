// The Instance browser's screen in a real browser, over the real routes (an in-memory runtime and a
// fake CDP endpoint behind them): the admin reads its state, stops and starts it by hand, and saves
// the allowlist. What each part shows is asserted by the React tests (`browser-app.test.tsx`).
import { expect, test } from '@playwright/test';
import { login } from './support/login.mts';

test('el admin ve el Instance browser, lo detiene y lo arranca a mano, y guarda los dominios permitidos', async ({ page }) => {
  await login(page);
  await page.getByRole('navigation', { name: 'Navegación' }).getByRole('button', { name: 'Instance browser', exact: true }).click();
  await expect(page).toHaveURL(/\/browser$/);
  const state = page.getByRole('region', { name: 'Estado del browser' });
  await expect(state).toContainText('en marcha');
  await expect(state).toContainText('Chrome/130.0');
  await expect(page.getByRole('region', { name: 'Sesiones con browser' })).toContainText('Inicio');

  await state.getByRole('button', { name: 'Detener' }).click();
  await expect(state).toContainText('detenido');
  await state.getByRole('button', { name: 'Arrancar' }).click();
  await expect(state).toContainText('en marcha');

  const domains = page.getByRole('textbox', { name: /uno por línea/ });
  await domains.fill('a.example, *.b.example');
  await page.getByRole('button', { name: 'Guardar dominios' }).click();
  await expect(domains).toHaveValue('a.example\n*.b.example');
  await page.reload();
  await expect(page.getByRole('textbox', { name: /uno por línea/ })).toHaveValue('a.example\n*.b.example');
  await page.getByRole('textbox', { name: /uno por línea/ }).fill('');
  await page.getByRole('button', { name: 'Guardar dominios' }).click();
});
