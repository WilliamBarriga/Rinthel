import { test, expect } from '@playwright/test';
import { createMember, login } from './support/login.mts';
import { DEMO_USER } from './support/scenario.mts';

test('the admin lands on Sesiones; the Sidebar lists exactly the registry and the way out', async ({ page }) => {
  await login(page);
  await expect(page.getByRole('heading', { name: `Hola, ${DEMO_USER.username}`, exact: true })).toBeVisible();
  const sidebar = page.getByRole('navigation', { name: 'Navegación' });
  for (const name of ['Sesiones', 'SOUL de la Instance', 'Apariencia', 'Usuarios', 'Ajustes']) {
    await expect(sidebar.getByRole('button', { name, exact: true })).toBeVisible();
  }
  for (const name of ['Buzones', 'Bandeja', 'Expertos', 'Browser', 'Registro del Guard']) {
    await expect(sidebar.getByRole('button', { name, exact: true })).toHaveCount(0);
  }
  await sidebar.getByRole('button', { name: 'Ajustes', exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole('heading', { name: 'Local model', exact: true })).toBeVisible();
  await sidebar.getByRole('button', { name: 'Cerrar sesión' }).click();
  await expect(page.getByPlaceholder('Usuario')).toBeVisible();
});

test('a member does not see the admin destinations and a deep link to them goes home', async ({ page, request }) => {
  const member = { username: 'shell-member', password: 'member-pass' };
  await createMember(request, member);
  await login(page, '/settings', member);
  await expect(page).toHaveURL(/\/$/);
  const sidebar = page.getByRole('navigation', { name: 'Navegación' });
  await expect(sidebar.getByRole('button', { name: 'Sesiones', exact: true })).toBeVisible();
  for (const name of ['Usuarios', 'Ajustes']) await expect(sidebar.getByRole('button', { name, exact: true })).toHaveCount(0);
  await page.goto('/users');
  await expect(page).toHaveURL(/\/$/);
});
