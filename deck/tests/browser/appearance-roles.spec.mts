import { expect, test } from '@playwright/test';
import { createMember, login } from './support/login.mts';

// Roles, palette and saved preferences per Estilo live in the React tests.
test('un miembro aplica su Estilo desde Apariencia, no ve la Marca y no envía nada a su Sesión', async ({ page, request }) => {
  const credentials = { username: 'member-style', password: 'member-pass' };
  await createMember(request, credentials);
  await login(page, '/', credentials);
  await page.getByRole('button', { name: 'Nuevo chat' }).click();
  await expect(page).toHaveURL(/\/sessions\/[\w-]+$/);
  const sessionUrl = page.url();
  const id = new URL(sessionUrl).pathname.split('/').pop()!;
  let prompts = 0;
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/prompt')) prompts++; });
  try {
    await page.getByRole('navigation', { name: 'Navegación' }).getByRole('button', { name: 'Apariencia', exact: true }).click();
    const panel = page.getByRole('region', { name: 'Personalización' });
    await expect(panel.getByRole('tab', { name: 'Marca', exact: true })).toHaveCount(0);
    for (const [label, layout] of [['Operación', 'operation'], ['Equilibrado', 'balanced']] as const) {
      await panel.getByRole('radio', { name: new RegExp(label) }).check();
      await panel.getByRole('button', { name: 'Aplicar preferencias', exact: true }).click();
      await expect(panel.getByText('Preferencias guardadas.', { exact: true })).toBeVisible();
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('data-layout', layout);
    }
    await page.goto(sessionUrl);
    await expect(page.getByRole('textbox', { name: 'Mensaje', exact: true })).toBeVisible();
    expect(prompts).toBe(0);
  } finally { await page.request.delete(`/api/sessions/${id}`); }
});
