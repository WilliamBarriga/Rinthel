import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VoiceFirstTurn, AUDIO_SYSTEM_RULE, audioSystemRules, audioMessage, voiceFirstSettings } from '../server/src/pi/voice-first.ts';
import { RINTHEL_PROVIDER_ID } from '../server/src/pi/rinthel-provider.ts';

/**
 * A voice Turn as pi's extension sees it: the `[Audio mode]` marker on the message, one stable system
 * rule that says what to do with it, and the first model call of the Turn without thinking, so the
 * first spoken words come sooner. The Local model is the only provider (`rinthel`).
 */
const ON = voiceFirstSettings({});
function setup(settings = ON, provider = RINTHEL_PROVIDER_ID) {
  const turn = new VoiceFirstTurn(settings), handlers = new Map<string, (...args: any[]) => any>();
  turn.extension({ on: (name: string, fn: any) => handlers.set(name, fn) });
  const payload = { messages: [{ role: 'system', content: AUDIO_SYSTEM_RULE }, { role: 'user', content: audioMessage('Latest request', ON) }], thinking_budget_tokens: 1024, chat_template_kwargs: { existing: true } };
  const request = () => handlers.get('before_provider_request')!({ payload }, { model: { provider } });
  return { turn, handlers, payload, request };
}

test('audio requests carry a marker and a stable conditional system rule', () => {
  assert.equal(audioMessage('Hello', ON), '[Audio mode]\nHello');
  assert.match(AUDIO_SYSTEM_RULE, /latest user request only/);
  assert.match(AUDIO_SYSTEM_RULE, /normal chat formatting/);
  assert.match(AUDIO_SYSTEM_RULE, /plain conversational text/);
  assert.match(AUDIO_SYSTEM_RULE, /Before every tool call or group of tool calls/);
});

test('voice mode never injects or mutates messages', () => {
  const { turn, payload, request, handlers } = setup(); turn.arm();
  const result = request();
  assert.equal(result.messages, payload.messages);
  assert.equal(handlers.has('before_agent_start'), false);
});

test('only the first call of a voice Turn skips thinking, leaving the saved request alone', () => {
  const { turn, handlers, payload, request } = setup(); turn.arm();
  assert.equal(request().chat_template_kwargs.enable_thinking, false);
  assert.equal(request().chat_template_kwargs.existing, true);
  assert.equal(request().thinking_budget_tokens, undefined);
  assert.equal(payload.thinking_budget_tokens, 1024);
  handlers.get('turn_end')!(); assert.equal(request(), undefined);
  turn.arm(); turn.reset(); assert.equal(request(), undefined);
  turn.arm(false); assert.equal(request(), undefined);
});

test('a model that is not the Local model is left alone', () => {
  const { turn, request } = setup(ON, 'other'); turn.arm();
  assert.equal(request(), undefined);
});

test('the switches turn thinking and the speaking rules back on', () => {
  const { turn, request } = setup(voiceFirstSettings({ VOICE_SKIP_FIRST_THINKING: 'false' })); turn.arm();
  assert.equal(request(), undefined);
  const off = voiceFirstSettings({ VOICE_RESPONSE_INSTRUCTIONS: 'false' });
  assert.deepEqual(audioSystemRules(off), []);
  assert.equal(audioMessage('Write a report', off), 'Write a report');
  assert.deepEqual(audioSystemRules(ON), [AUDIO_SYSTEM_RULE]);
});
