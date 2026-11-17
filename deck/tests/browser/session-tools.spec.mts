// The tools of a Sesión in a real browser, logic only: focus and keyboard, the draft and the selected
// Canvas surviving a theme change without reopening the event stream, the Instance browser's live
// frame surviving its panel being hidden, and the panel's width kept across a reload. What the panels
// show is asserted by the React tests (`chat-app.test.tsx`, `canvas-panel.test.tsx`, `browser-app.test.tsx`).
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

test('navegador de la Sesión: la vista conserva su página al ocultarla y al cambiar de tema, y el admin lo activa para la Sesión', async ({ page }) => {
  let frames = 0;
  // The view is KasmVNC behind `/browser-ui`; here a page with a field stands in for it.
  await page.route('**/browser-ui/', route => { frames++; return route.fulfill({ contentType: 'text/html', body: '<label>Texto del navegador<input aria-label="Texto del navegador"></label>' }); });
  await login(page);
  const id = await newChat(page);
  try {
    const composer = page.getByRole('textbox', { name: 'Mensaje', exact: true });
    await composer.fill('Borrador activo');
    const toggle = page.getByRole('button', { name: 'Navegador de la Sesión' });
    await toggle.click();
    const panel = page.getByRole('complementary', { name: 'Navegador de la Sesión' });
    await panel.getByRole('checkbox').check();
    await expect.poll(async () => (await (await page.request.get('/api/browser')).json()).sessions.map((s: { id: string }) => s.id)).toContain(id);
    const field = page.frameLocator('iframe[title="Navegador de la Sesión"]').getByRole('textbox', { name: 'Texto del navegador' });
    await field.fill('Página en curso');
    // Closing hides the frame, never tears it down: the page and what was typed stay.
    await panel.getByRole('button', { name: 'Volver al chat' }).click();
    await expect(panel).toBeHidden();
    await toggle.click();
    await expect(field).toHaveValue('Página en curso');
    await setTheme(page, 'Oscuro');
    await expect(field).toHaveValue('Página en curso');
    await expect(composer).toHaveValue('Borrador activo');
    expect(frames).toBe(1);
  } finally { await page.request.delete(`/api/sessions/${id}`); }
});

test('el ancho del panel del navegador se ajusta por teclado y se conserva al recargar', async ({ page }) => {
  await page.route('**/browser-ui/', route => route.fulfill({ contentType: 'text/html', body: '<p>Navegador aislado</p>' }));
  await login(page);
  const id = await newChat(page);
  try {
    await page.getByRole('button', { name: 'Navegador de la Sesión' }).click();
    const handle = page.getByRole('separator', { name: 'Ancho de herramientas' });
    const width = async () => Number(await handle.getAttribute('aria-valuenow'));
    await handle.focus();
    const before = await width();
    await page.keyboard.press('ArrowLeft');
    await expect.poll(width).not.toBe(before);
    const resized = await width();
    const panel = page.getByRole('complementary', { name: 'Navegador de la Sesión' });
    expect(Math.round((await panel.boundingBox())!.width)).toBe(resized);
    await page.reload();
    await page.getByRole('button', { name: 'Navegador de la Sesión' }).click();
    await expect.poll(width).toBe(resized);
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
