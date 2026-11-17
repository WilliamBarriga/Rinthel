import { expect, test } from '@playwright/test';
import { login } from './support/login.mts';

test('un workspace y su tarea conservan historial, recarga y foco de navegación', async ({ page }) => {
  await login(page, '/');
  await page.getByRole('textbox', { name: 'Nuevo workspace' }).fill('contratos');
  await page.getByRole('button', { name: 'Crear', exact: true }).click();
  await page.getByRole('combobox', { name: 'Workspace' }).selectOption('contratos');
  await page.getByRole('button', { name: 'Nueva tarea', exact: true }).click();
  await expect(page).toHaveURL(/\/sessions\/[\w-]+$/);
  const taskUrl = page.url();
  await expect(page.getByRole('heading', { name: /contratos/ })).toBeVisible();
  await page.getByRole('button', { name: 'Volver a Sesiones' }).click();
  await expect(page).toHaveURL(/\/$/);
  const tasks = page.getByRole('region', { name: 'Tareas' });
  await expect(tasks.getByRole('listitem')).toHaveCount(1);
  await page.goBack();
  await expect(page).toHaveURL(taskUrl);
  await page.goForward();
  await expect(page).toHaveURL(/\/$/);
  await page.reload();
  await expect(tasks.getByRole('listitem')).toHaveCount(1);
  await tasks.getByRole('listitem').getByRole('button').first().click();
  await expect(page).toHaveURL(taskUrl);
});
