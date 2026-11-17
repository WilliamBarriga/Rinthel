import { test, expect } from '@playwright/test';
import { login } from './support/login.mts';

// The Canvas stream is scripted at the public SSE transport (`/canvases/events`): the Agent's writes
// arrive as `create`/`update`/`focus` frames. Everything else is the real app over the real routers.
test('canvas streams on the stage, retains a partial draft, downloads and is read only (only the Agent writes)', async ({ page }) => {
  const failures: string[] = [];
  page.on('pageerror', e => failures.push(e.message));
  await page.addInitScript(() => {
    const Real = window.EventSource;
    class FakeEvents {
      onmessage: any; onopen: any; onerror: any;
      constructor() {
        (window as any).canvasStream = this;
        setTimeout(() => { this.onopen?.(); this.onmessage?.({ data: JSON.stringify({ type: 'snapshot', canvases: [] }) }); (window as any).canvasStreamReady = true; }, 100);
      }
      addEventListener() {}
      close() {}
    }
    (window as any).EventSource = function (url: string, init?: EventSourceInit) {
      return /\/canvases\/events$/.test(String(url)) ? new FakeEvents() : new Real(url, init);
    };
  });
  await login(page);
  await page.getByRole('button', { name: 'Nuevo chat' }).click();
  await expect(page).toHaveURL(/\/sessions\/[\w-]+$/);
  await page.waitForFunction(() => (window as any).canvasStreamReady);
  const row: any = { id: 'canvas-1', session_id: 'x', kind: 'markdown', title: 'A live document', content: '', revision: 0, status: 'writing', active_call: 'call-1', updated_at: '', persisted: false };
  const send = (type: string, canvas: unknown) => page.evaluate(([t, c]) => (window as any).canvasStream.onmessage({ data: JSON.stringify({ type: t, canvas: c }) }), [type, canvas] as const);

  // Creation opens the panel before the first write.
  await send('create', { ...row, status: 'saved', active_call: null });
  await expect(page.getByLabel('Espacio de Canvas de la Sesión')).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar Canvas' }).click();
  await expect(page.getByLabel('Espacio de Canvas de la Sesión')).toBeHidden();

  // A write of a new call reopens it and streams the text.
  row.content = '# A live document\n\nThe first sentence.'; row.revision = 1;
  await send('update', row);
  await expect(page.getByLabel('Espacio de Canvas de la Sesión')).toBeVisible();
  await expect(page.locator('.canvas-document')).toContainText('The first sentence.');
  await expect(page.getByText('Escribiendo en vivo')).toBeVisible();
  row.content += ' Another sentence appears.'; row.revision = 2;
  await send('update', row);
  await expect(page.locator('.canvas-document')).toContainText('Another sentence appears.');

  // An interrupted write keeps the partial draft.
  row.status = 'interrupted'; row.active_call = null;
  await send('update', row);
  await expect(page.getByText('Borrador parcial conservado', { exact: false })).toBeVisible();

  // The person downloads the `.md`.
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Descargar Canvas', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('A live document.md');

  // Read only: the panel has no control to edit, store or delete.
  for (const name of ['Edit canvas content', 'Store canvas', 'Delete canvas']) await expect(page.getByLabel(name, { exact: true })).toHaveCount(0);

  // The Agent focusing another document selects it.
  await send('focus', { id: 'read-doc', session_id: 'x', kind: 'markdown', title: 'Document being read', content: 'The AI is reading this document.', revision: 1, status: 'saved', active_call: null, persisted: true });
  await expect(page.getByLabel('Seleccionar Canvas')).toHaveValue('read-doc');
  await expect(page.locator('.canvas-document')).toContainText('The AI is reading this document.');
  expect(failures).toEqual([]);
  await page.request.delete('/api/sessions/' + new URL(page.url()).pathname.split('/').pop());
});
