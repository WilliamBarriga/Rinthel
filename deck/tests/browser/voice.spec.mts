// Voice in a real browser, on the harness `web/tests/voice.html`: the real chat and voice mode, the
// real Silero VAD on a synthetic microphone fed with `tests/fixtures/jfk.wav`, and the voice routes
// answered here. What each screen shows is asserted by the React tests (`voice-app.test.tsx`).
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { setTheme } from './support/appearance.mts';

const sample = readFileSync(new URL('../fixtures/jfk.wav', import.meta.url));
/** The reader's voice on, and the Instance with both stt and tts active. */
const VOICE_ON = { enabled: true, language: 'auto', stt: true, tts: true, statusSpeech: true, comparison: false, ttsPrefetch: false, sentenceChunks: false, pipelineMode: 'parallel' };

test.beforeEach(async ({ page }) => {
  await page.route('**/api/voice', route => route.fulfill({ json: VOICE_ON }));
  await page.route('**/test-speech.wav', route => route.fulfill({ body: sample, contentType: 'audio/wav' }));
});

const start = (page: import('@playwright/test').Page) => page.getByRole('button', { name: 'Activar voz manos libres' });
const end = (page: import('@playwright/test').Page) => page.getByRole('button', { name: 'Terminar modo voz' });
const status = (page: import('@playwright/test').Page) => page.locator('.voice-stage').getByRole('status');
const message = (page: import('@playwright/test').Page) => page.getByRole('textbox', { name: 'Mensaje' });

test('la detección real envía turnos, admite interrupción y libera el micrófono', async ({ page }) => {
  const failures: string[] = [];
  page.on('pageerror', e => failures.push(e.message));
  await page.route('**/voice/transcribe', route => {
    expect(route.request().postDataBuffer()?.subarray(0, 4).toString()).toBe('RIFF');
    return route.fulfill({ json: { text: 'A test voice turn.' } });
  });
  await page.route('**/voice/speech', route => route.fulfill({ body: sample, contentType: 'audio/wav' }));
  await page.goto('/tests/voice.html');
  await message(page).fill('Conserva este borrador');
  await page.getByRole('button', { name: 'Perfil de latencia de voz' }).click();
  await start(page).click();
  await expect(end(page)).toBeVisible({ timeout: 25000 });
  await expect(status(page)).toContainText('Escuchando');
  await expect(message(page)).toBeHidden();
  // The theme changes while the real VAD holds the microphone: the same stream stays.
  for (const theme of ['Claro', 'Oscuro', 'Cyberpunk'] as const) {
    await setTheme(page, theme);
    await expect(status(page)).toContainText('Escuchando');
    await page.getByRole('button', { name: 'Check mic tracks' }).click();
    await expect(page.getByTestId('tracks')).toHaveText('live:true');
    await expect(page.getByTestId('mic-requests')).toHaveText('1');
  }

  await expect(page.getByText('We can work through it together.')).toBeHidden();
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await expect(status(page)).toContainText('Te escucho');
  await expect(page.getByTestId('sent')).toHaveText('1', { timeout: 12000 });
  await expect(page.getByTestId('voice-send')).toHaveText('true');
  await expect(status(page)).toContainText('Hablando');
  const profile = page.getByLabel('Latencia de voz', { exact: true });
  await expect(profile).toContainText('desde la última voz detectada hasta el audio de la respuesta');
  await expect(profile).toContainText('Detección del turno');
  const timingDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Descargar informe de tiempos' }).click();
  expect((await timingDownload).suggestedFilename()).toBe('voice-latency.json');
  const { readFile } = await import('node:fs/promises');
  const timing = JSON.parse(await readFile((await (await timingDownload).path())!, 'utf8'));
  expect(timing[0]).toMatchObject({ status: 'complete', marks: expect.arrayContaining([expect.objectContaining({ name: 'reply_tts_request' })]) });
  await page.getByRole('button', { name: 'Cerrar perfil de voz' }).click();

  // Speaking over the Agent's reply interrupts it, and the new turn is sent.
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await expect(status(page)).toContainText('Te escucho');
  await expect(page.getByTestId('aborted')).toHaveText('1');
  await expect(page.getByTestId('sent')).toHaveText('2', { timeout: 12000 });
  await end(page).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('ended:true');
  await expect(start(page)).toBeVisible();
  await expect(message(page)).toHaveValue('Conserva este borrador');
  await expect(page.getByText('We can work through it together.')).toBeVisible();
  expect(failures).toEqual([]);
});

test('cancelar mientras carga el modelo de detección libera el micrófono sin enviar nada', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/silero_vad_v5.onnx', async route => { await gate; await route.continue(); });
  await page.goto('/tests/voice.html');
  const request = page.waitForRequest('**/silero_vad_v5.onnx');
  await start(page).click();
  await request;
  await expect(page.getByRole('button', { name: 'Silenciar micrófono', exact: true })).toBeDisabled();
  await end(page).click();
  release();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('ended:true');
  await expect(page.getByTestId('sent')).toHaveText('0');
  await expect(start(page)).toBeVisible();
});

test('silenciar mantiene la respuesta hablada y los diálogos; terminar devuelve el chat', async ({ page }) => {
  await page.route('**/voice/transcribe', route => route.fulfill({ json: { text: 'A test voice turn.' } }));
  await page.route('**/voice/speech', route => route.fulfill({ body: sample, contentType: 'audio/wav' }));
  await page.goto('/tests/voice.html');
  await start(page).click();
  await expect(status(page)).toHaveText('Escuchando', { timeout: 25000 });
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await expect(page.locator('.voice-orb')).toHaveAttribute('data-mode', 'input');
  await expect(page.getByTestId('sent')).toHaveText('1', { timeout: 12000 });
  await expect(page.locator('.voice-orb')).toHaveAttribute('data-mode', 'output');
  await page.getByRole('button', { name: 'Silenciar micrófono', exact: true }).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('live:false');
  await expect(page.locator('.voice-orb')).toHaveAttribute('data-mode', 'output');
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await page.waitForTimeout(4200); // Longer than the injected speech plus the end-of-turn silence.
  await expect(page.getByTestId('sent')).toHaveText('1');
  await expect(page.getByTestId('aborted')).toHaveText('0');
  await page.getByRole('button', { name: 'Show options' }).click();
  await page.getByRole('button', { name: 'Correr pruebas', exact: true }).click();
  await expect(page.getByTestId('selected')).toHaveText('1');
  await page.getByRole('button', { name: 'Activar micrófono' }).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('live:true');
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await expect(page.getByTestId('sent')).toHaveText('2', { timeout: 12000 });
  await end(page).click();
  await expect(message(page)).toBeVisible();
});

test('la voz sintetiza la frase siguiente mientras suena la anterior y lo cancela al terminar', async ({ page }) => {
  const failures: string[] = []; page.on('pageerror', e => failures.push(e.message));
  const pcm = Buffer.alloc(24000 * 2 * 5);
  for (let i = 0; i < pcm.length / 2; i++) pcm.writeInt16LE(Math.round(Math.sin(i * 2 * Math.PI * 220 / 24000) * 5000), i * 2);
  const texts: string[] = [];
  await page.route('**/voice/speech', route => {
    expect(route.request().headers().accept).toBe('audio/pcm');
    texts.push(route.request().postDataJSON().text);
    return route.fulfill({ body: pcm, headers: { 'content-type': 'audio/pcm', 'x-sample-rate': '24000' } });
  });
  await page.goto('/tests/voice.html');
  await start(page).click();
  await expect(status(page)).toHaveText('Escuchando', { timeout: 25000 });
  await page.getByRole('button', { name: 'Stream reply', exact: true }).click();
  await expect(page.locator('.voice-orb')).toHaveAttribute('data-mode', 'output');
  expect(texts).toEqual(['Here is the first sentence.']);
  await page.getByRole('button', { name: 'Finish reply', exact: true }).click();
  // The first phrase lasts five seconds: the second request has to start while it plays.
  await expect.poll(() => texts.length, { timeout: 1500 }).toBe(2);
  await expect(page.locator('.voice-orb')).toHaveAttribute('data-mode', 'output');
  expect(texts).toEqual(['Here is the first sentence.', 'More text follows.']);
  await end(page).click();
  await expect(message(page)).toBeVisible();
  expect(failures).toEqual([]);
});

test('PCM lento se junta en un solo búfer sin cortes, aun con muestras partidas', async ({ page }) => {
  await page.goto('/tests/voice.html');
  const result = await page.evaluate(async () => {
    const { playPcmStream } = await import('/src/voice/pcm-stream.ts');
    const audio = new AudioContext(); await audio.resume();
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    let started = false, sourceCount = 0;
    const original = audio.createBufferSource.bind(audio);
    audio.createBufferSource = () => { sourceCount++; return original(); };
    const body = new ReadableStream<Uint8Array>({ start(c) { writer = c; } });
    const pending = playPcmStream(body, audio, audio.destination, new AbortController().signal, () => { started = true; });
    writer.enqueue(new Uint8Array([0]));
    writer.enqueue(new Uint8Array(4801));
    await new Promise(resolve => setTimeout(resolve, 300)); // A producer slower than the 100 ms of audio it has sent.
    const startedTooEarly = started;
    writer.enqueue(new Uint8Array(4800)); writer.close();
    await pending; await audio.close();
    return { startedTooEarly, started, sourceCount };
  });
  expect(result).toEqual({ startedTooEarly: false, started: true, sourceCount: 1 });
});

test('terminar cancela el búfer de PCM antes de que suene nada', async ({ page }) => {
  await page.goto('/tests/voice.html');
  const result = await page.evaluate(async () => {
    const { playPcmStream } = await import('/src/voice/pcm-stream.ts');
    const audio = new AudioContext(); await audio.resume();
    let cancelled = false, started = false;
    const body = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new Uint8Array(4800)); }, cancel() { cancelled = true; } });
    const abort = new AbortController();
    const pending = playPcmStream(body, audio, audio.destination, abort.signal, () => { started = true; }).then(() => 'finished', () => 'aborted');
    await new Promise(resolve => setTimeout(resolve, 50)); abort.abort();
    const outcome = await pending; await audio.close();
    return { started, cancelled, outcome };
  });
  expect(result).toEqual({ started: false, cancelled: true, outcome: 'aborted' });
});

test('la transcripción en vivo empieza antes de que acabe el turno y muestra lo reconocido', async ({ page }) => {
  await page.route('**/voice/transcribe', route => route.fulfill({ json: { text: 'Recognized while you speak.' } }));
  await page.route('**/voice/speech', route => route.fulfill({ body: sample, contentType: 'audio/wav' }));
  await page.goto('/tests/voice.html');
  await start(page).click();
  await expect(status(page)).toHaveText('Escuchando', { timeout: 25000 });
  const request = page.waitForRequest('**/voice/transcribe');
  await page.getByRole('button', { name: 'Inject speech' }).click();
  await request;
  await expect(page.getByTestId('sent')).toHaveText('0');
  await expect(page.getByLabel('Transcripción en vivo')).toHaveText('Recognized while you speak.');
  await expect(page.getByTestId('sent')).toHaveText('1', { timeout: 12000 });
  await end(page).click();
});

test('la lectura del prompt y la compactación se ven bajo el orbe', async ({ page }) => {
  await page.goto('/tests/voice.html');
  await start(page).click();
  await expect(status(page)).toHaveText('Escuchando', { timeout: 25000 });
  await page.getByRole('button', { name: 'Show prefill', exact: true }).click();
  await expect(page.locator('.voice-stage').getByRole('progressbar', { name: 'Procesamiento del prompt' })).toHaveAttribute('aria-valuenow', '40');
  await page.getByRole('button', { name: 'Start compaction', exact: true }).click();
  const bar = page.locator('.voice-stage').getByRole('progressbar', { name: 'Compactación de la conversación' });
  await expect(bar).toBeVisible();
  await expect(bar).not.toHaveAttribute('aria-valuenow');
  await page.getByRole('button', { name: 'End compaction', exact: true }).click();
  await expect(bar).toHaveCount(0);
  await end(page).click();
});

test('sin un Local model de tts activo la voz no aparece ni pide el micrófono', async ({ page }) => {
  await page.route('**/api/voice', route => route.fulfill({ json: { ...VOICE_ON, tts: false } }));
  await page.goto('/tests/voice.html');
  await expect(message(page)).toBeVisible();
  await expect(start(page)).toHaveCount(0);
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('mic-requests')).toHaveText('0');
});

test('efectos de sonido y perfil responden, y el micrófono se libera', async ({ page }) => {
  await page.route('**/voice/speech', route => route.fulfill({ body: sample, contentType: 'audio/wav' }));
  await page.goto('/tests/voice.html');
  await page.getByRole('button', { name: 'Perfil de latencia de voz' }).click();
  const profile = page.getByLabel('Latencia de voz', { exact: true });
  await expect(profile.getByRole('button', { name: 'Descargar informe de tiempos' })).toBeDisabled();
  await profile.getByRole('button', { name: 'Cerrar perfil de voz' }).click();
  await expect(profile).toHaveCount(0);
  await start(page).click();
  await expect(status(page)).toHaveText('Escuchando', { timeout: 25000 });
  await page.getByRole('button', { name: 'Silenciar efectos de sonido' }).click();
  await expect(page.getByRole('button', { name: 'Activar efectos de sonido' })).toHaveAttribute('aria-pressed', 'false');
  await page.getByRole('button', { name: 'Activar efectos de sonido' }).click();
  await expect(page.getByRole('button', { name: 'Silenciar efectos de sonido' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Use terminal', exact: true }).click();
  await expect(page.getByLabel('Actividad de herramientas')).toContainText('Ejecutando un comando');
  await end(page).click();
  await page.getByRole('button', { name: 'Check mic tracks' }).click();
  await expect(page.getByTestId('tracks')).toHaveText('ended:true');
});

for (const ending of ['Disconnect microphone', 'Unmount workspace'])
  test(`la voz libera el micrófono: ${ending}`, async ({ page }) => {
    await page.goto('/tests/voice.html');
    await start(page).click();
    await expect(status(page)).toHaveText('Escuchando', { timeout: 25000 });
    await page.getByRole('button', { name: ending }).click();
    await page.getByRole('button', { name: 'Check mic tracks' }).click();
    await expect(page.getByTestId('tracks')).toHaveText('ended:true');
    if (ending === 'Disconnect microphone') {
      await expect(page.locator('.voice-stage')).toHaveCount(0);
      await expect(page.getByRole('alert')).toContainText('El micrófono se desconectó');
    }
  });
