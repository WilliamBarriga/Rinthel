// Navigation in a real browser: deep link, Back/Forward and unknown paths. What each destination shows
// is asserted by the React tests.
import { expect, test } from '@playwright/test';
import { DEMO_USER } from './support/scenario.mts';
import { login } from './support/login.mts';

test('deep link, Back, Forward and the signed-in name in the Sidebar', async ({ page }) => {
  await login(page, '/soul');
  await expect(page).toHaveURL(/\/soul$/);
  await expect(page.getByRole('heading', { name: 'SOUL de la Instance', exact: true })).toBeVisible();
  const sidebar = page.getByRole('navigation', { name: 'Navegación' });
  await expect(sidebar).toContainText(DEMO_USER.username);
  await expect(sidebar.getByRole('button', { name: 'SOUL de la Instance' })).toHaveAttribute('aria-current', 'page');
  await sidebar.getByRole('button', { name: 'Apariencia', exact: true }).click();
  await expect(page).toHaveURL(/\/appearance$/);
  await expect(page.getByRole('region', { name: 'Personalización' })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/soul$/);
  await expect(page.getByRole('heading', { name: 'SOUL de la Instance', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(/\/appearance$/);
  await sidebar.getByRole('button', { name: 'Sesiones', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: `Hola, ${DEMO_USER.username}`, exact: true })).toBeVisible();
});

test('a path that is not a destination goes home; an unknown Session opens an empty chat', async ({ page }) => {
  await login(page, '/');
  await page.goto('/prototype/shell');
  await expect(page).toHaveURL(/\/$/);
  await page.goto('/sessions/does-not-exist');
  await expect(page.getByRole('region', { name: 'Transcripción' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Navegación' })).toBeVisible();
});
