// What only a real browser proves for the platform: the image decoder behind the logo upload and the
// History API (query/hash on Back/Forward). Navigation, rename and delete are asserted by the React tests.
import { test, expect } from '@playwright/test';
import { login } from './support/login.mts';

test('el logo se decodifica en PNG/JPEG/WebP, rechaza lo inválido sin cambiar la vista previa y se quita', async ({ page }) => {
  await login(page, '/appearance');
  const panel = page.getByRole('region', { name: 'Personalización' });
  await panel.getByRole('tab', { name: 'Marca', exact: true }).click();
  const original = (await (await page.request.get('/api/appearance')).json()).branding;
  const images = await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = c.height = 24;
    const ctx = c.getContext('2d')!; ctx.fillStyle = 'red'; ctx.fillRect(0, 0, 24, 24);
    return ['image/png', 'image/jpeg', 'image/webp'].map(type => ({ type, data: c.toDataURL(type) }));
  });
  const wide = await page.evaluate(() => { const c = document.createElement('canvas'); c.width = 4097; c.height = 1; return c.toDataURL('image/png'); });
  try {
    const input = panel.getByLabel('Logo claro', { exact: true });
    const preview = panel.getByRole('img', { name: 'Vista previa del logo claro', exact: true });
    for (const image of images) {
      await input.setInputFiles({ name: 'logo', mimeType: image.type, buffer: Buffer.from(image.data.split(',')[1], 'base64') });
      await expect(preview).toHaveAttribute('src', image.data);
    }
    for (const [mimeType, buffer] of [
      ['image/svg+xml', Buffer.from('<svg/>')],
      ['image/png', Buffer.alloc(250001)],
      ['image/png', Buffer.from('not a raster')],
      ['image/png', Buffer.from(wide.split(',')[1], 'base64')],
    ] as const) {
      await input.setInputFiles({ name: 'invalid', mimeType, buffer });
      await expect(panel.getByRole('alert')).toBeVisible();
      await expect(preview).toHaveAttribute('src', images[2].data);
    }
    await panel.getByRole('button', { name: 'Quitar logo claro', exact: true }).click();
    await expect(preview).toHaveCount(0);
    expect((await (await page.request.get('/api/appearance')).json()).branding).toEqual(original);
  } finally { await page.request.put('/api/appearance/brand', { data: original }); }
});

test('el historial conserva query y hash al volver y avanzar', async ({ page }) => {
  await login(page, '/users?q=demo#lista');
  await expect(page.getByRole('heading', { name: 'Usuarios', exact: true })).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Buscar usuario' })).toHaveValue('demo');
  await page.getByRole('navigation', { name: 'Navegación' }).getByRole('button', { name: 'Sesiones', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/users\?q=demo#lista$/);
  await expect(page.getByRole('searchbox', { name: 'Buscar usuario' })).toHaveValue('demo');
  await page.goForward();
  await expect(page).toHaveURL(/\/$/);
});
