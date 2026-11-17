// The Session's tools while voice mode holds the microphone, on the harness `web/tests/voice.html`:
// the Canvas and the Session's browser panel open and close beside the voice stage, the controls of
// voice answer, and the same microphone stream lives through all of it until voice mode ends.
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const sample = readFileSync(new URL('../fixtures/jfk.wav', import.meta.url));
const VOICE_ON = { enabled: true, language: 'auto', stt: true, tts: true, statusSpeech: true, comparison: false, ttsPrefetch: false, sentenceChunks: false, pipelineMode: 'parallel' };

test.beforeEach(async ({ page }) => {
  await page.route('**/api/voice', r => r.fulfill({ json: VOICE_ON }));
  await page.route('**/voice/speech', r => r.fulfill({ body: sample, contentType: 'audio/wav' }));
  await page.route('**/test-speech.wav', r => r.fulfill({ body: sample, contentType: 'audio/wav' }));
  await page.route('**/browser-ui/', r => r.fulfill({ contentType: 'text/html', body: '<p>Browser conservado</p>' }));
});

test('voz: Canvas, navegador de la Sesión, sonido y micrófono responden sin soltar el micrófono', async ({ page }) => {
  await page.goto('/tests/voice.html');
  await page.getByRole('button', { name: 'Activar voz manos libres' }).click();
  const stage = page.getByRole('region', { name: 'Conversación por voz' });
  await expect(stage.getByRole('status')).toHaveText('Escuchando', { timeout: 25000 });

  await page.getByRole('button', { name: 'Canvas de la Sesión', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Espacio de Canvas de la Sesión' })).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar Canvas', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Espacio de Canvas de la Sesión' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Navegador de la Sesión', exact: true }).click();
  const browser = page.getByRole('complementary', { name: 'Navegador de la Sesión' });
  await expect(browser).toBeVisible();
  await expect(browser.locator('iframe')).toHaveAttribute('src', '/browser-ui/');
  await expect(stage).toBeVisible();
  await browser.getByRole('button', { name: 'Volver al chat' }).click();
  await expect(browser).toBeHidden();

  await page.getByRole('button', { name: 'Silenciar efectos de sonido' }).click();
  await page.getByRole('button', { name: 'Activar efectos de sonido' }).click();
  await page.getByRole('button', { name: 'Silenciar micrófono', exact: true }).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('live:false');
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('live:true');
  await expect(page.getByTestId('mic-requests')).toHaveText('1');

  await page.getByRole('button', { name: 'Terminar modo voz' }).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('ended:true');
});

test('voz: un STT caído no envía el turno, lo dice y deja terminar', async ({ page }) => {
  await page.route('**/voice/transcribe', r => r.fulfill({ status: 502, json: { error: 'El STT respondió HTTP 500' } }));
  await page.goto('/tests/voice.html');
  await page.getByRole('button', { name: 'Activar voz manos libres' }).click();
  await expect(page.locator('.voice-stage').getByRole('status')).toHaveText('Escuchando', { timeout: 25000 });
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await expect(page.locator('.voice-stage').getByRole('alert')).toContainText('El STT respondió HTTP 500', { timeout: 15000 });
  await expect(page.getByTestId('sent')).toHaveText('0');
  await page.getByRole('button', { name: 'Terminar modo voz' }).click();
  await expect(page.getByRole('textbox', { name: 'Mensaje' })).toBeVisible();
});
