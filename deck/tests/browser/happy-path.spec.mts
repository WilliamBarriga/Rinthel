import { expect, test } from '@playwright/test';
import { DEMO_USER, NOTE_REPLY, REPLY } from './support/scenario.mts';

// The demo's happy path, end to end through the real web app and the real Deck routers behind it
// (`support/fake-deck-app.mts` says what is real; only pi is a script).
test('login, chat, reply, ui Canvas and its «preguntar al agente» note read in the next turn', async ({ page }) => {
  const failures: string[] = [];
  page.on('pageerror', (e) => failures.push(e.message));

  // Login: a wrong password stays on the form, the right one gets in.
  await page.goto('/');
  await page.getByPlaceholder('Usuario').fill(DEMO_USER.username);
  await page.getByPlaceholder('Contraseña').fill('wrong');
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(page.getByPlaceholder('Usuario')).toBeVisible();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByPlaceholder('Contraseña').fill(DEMO_USER.password);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(page.getByRole('heading', { name: `Hola, ${DEMO_USER.username}`, exact: true })).toBeVisible();

  // A new chat with the Agent.
  await page.getByRole('button', { name: 'Nuevo chat' }).click();
  await expect(page).toHaveURL(/\/sessions\/[\w-]+$/);
  const url = page.url();

  // The reply, and the Canvas the Agent wrote.
  await page.getByRole('textbox', { name: 'Mensaje' }).fill('¿Puedes armar un tablero?');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText(REPLY)).toBeVisible();
  const canvas = page.getByRole('region', { name: 'Espacio de Canvas de la Sesión' });
  await expect(canvas).toBeVisible();
  await expect(canvas).toContainText('Tablero de prueba');

  // «Preguntar al agente» leaves a note and starts no turn; the Agent reads it in the next one.
  await canvas.getByRole('button', { name: 'Preguntar al agente' }).click();
  await expect(canvas.getByText('Enviado al Agente. Lo leerá en su próximo turno.')).toBeVisible();
  await expect(page.getByText(NOTE_REPLY)).toHaveCount(0);
  await page.getByRole('textbox', { name: 'Mensaje' }).fill('¿Algo más?');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText(`${NOTE_REPLY} Explica la cláusula de exclusiones.`)).toBeVisible();

  // Back to the list: the chat is there, and survives a reload.
  await page.getByRole('button', { name: 'Volver a Sesiones' }).click();
  await expect(page.getByRole('region', { name: 'Chats con el Agente' }).getByRole('listitem').first()).toBeVisible();
  await page.goto(url);
  await expect(page.getByText(REPLY)).toBeVisible();
  expect(failures).toEqual([]);
});
