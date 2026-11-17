// The SOUL de la Instance in a real browser: the admin edits and saves it with the keyboard and it
// survives a reload; a member reads the same text and cannot edit it. Presentation and errors live in
// the React tests.
import { test, expect } from '@playwright/test';
import { createMember, login } from './support/login.mts';

const SOUL = 'Contenido de la Instance\n';

test('el administrador edita y guarda la SOUL, y un miembro la lee sin poder cambiarla', async ({ page, request }) => {
  await login(page, '/soul');
  const editor = page.getByRole('textbox', { name: 'Contenido de la SOUL de la Instance' });
  await expect(editor).not.toHaveJSProperty('readOnly', true);
  await editor.fill(SOUL);
  const save = page.getByRole('button', { name: 'Guardar', exact: true });
  await save.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: /Guardada/ })).toBeVisible();
  await page.reload();
  await expect(editor).toHaveValue(SOUL);

  const member = { username: 'soul-member', password: 'member-pass' };
  await createMember(request, member);
  await page.request.post('/api/auth/logout');
  await page.context().clearCookies();
  await login(page, '/soul', member);
  const memberView = page.getByRole('textbox', { name: 'Contenido de la SOUL de la Instance' });
  await expect(memberView).toHaveValue(SOUL);
  await expect(memberView).toHaveJSProperty('readOnly', true);
  await expect(page.getByRole('button', { name: 'Guardar', exact: true })).toHaveCount(0);
  await expect(page.getByText('La edita el administrador.')).toBeVisible();
});
