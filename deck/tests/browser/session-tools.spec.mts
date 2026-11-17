// The tools of a Sesión in a real browser, logic only: focus and keyboard, the draft and the selected
// Canvas surviving a theme change without reopening the event stream. What the panel shows is asserted
// by the React tests (`chat-app.test.tsx`, `canvas-panel.test.tsx`).
import { expect, test, type Page } from '@playwright/test';
import { REPLY } from './support/scenario.mts';
import { login } from './support/login.mts';
import { resetAppearanceAfterTest, setTheme } from './support/appearance.mts';

resetAppearanceAfterTest();

async function newChat(page: Page) {
  await page.getByRole('button', { name: 'Nuevo chat' }).click();
  await expect(page).toHaveURL(/\/sessions\/[\w-]+$/);
  return new URL(page.url()).pathname.split('/').pop()!;
}

test('Sesión: Canvas por teclado y borrador conservado al cambiar de tema', async ({ page }) => {
  await login(page);
  const id = await newChat(page);
  try {
    const composer = page.getByRole('textbox', { name: 'Mensaje', exact: true });
    await composer.fill('Arma un tablero.');
    await composer.press('Enter'); // Enter sends, Shift+Enter would not
    await expect(page.getByText(REPLY)).toBeVisible();
    const canvas = page.getByRole('region', { name: 'Espacio de Canvas de la Sesión' });
    await expect(canvas).toBeVisible();
    const selected = await page.getByRole('combobox', { name: 'Seleccionar Canvas' }).inputValue();

    // The toggle closes and reopens the panel from the keyboard.
    const toggle = page.getByRole('button', { name: 'Canvas de la Sesión', exact: true });
    await toggle.focus();
    await page.keyboard.press('Enter');
    await expect(canvas).toBeHidden();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await page.keyboard.press('Enter');
    await expect(canvas).toBeVisible();

    await composer.fill('Borrador de seguimiento sin enviar');
    let streams = 0;
    page.on('request', request => { if (/\/events(\?|$)/.test(request.url())) streams++; });
    await setTheme(page, 'Oscuro');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(composer).toHaveValue('Borrador de seguimiento sin enviar');
    await expect(page.getByRole('combobox', { name: 'Seleccionar Canvas' })).toHaveValue(selected);
    await expect(canvas).toContainText('Tablero de prueba');
    expect(streams).toBe(0);
  } finally { await page.request.delete(`/api/sessions/${id}`); }
});

test('Enter envía y Shift+Enter no; el botón de enviar espera texto', async ({ page }) => {
  await login(page);
  const id = await newChat(page);
  try {
    await expect(page.getByRole('button', { name: 'Enviar' })).toBeDisabled();
    const composer = page.getByRole('textbox', { name: 'Mensaje', exact: true });
    await composer.fill('línea 1');
    await composer.press('Shift+Enter');
    await expect(page.getByText(REPLY)).toHaveCount(0);
    await composer.press('Enter');
    await expect(page.getByText(REPLY)).toBeVisible();
  } finally { await page.request.delete(`/api/sessions/${id}`); }
});
