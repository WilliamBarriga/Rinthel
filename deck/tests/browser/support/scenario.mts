/** What the specs and the fake Deck agree on: who logs in and what the Agent's scripted turn says. */
export const DEMO_USER = { username: 'demo', password: 'demo-pass' };
export const REPLY = 'Listo: armé un tablero con una pregunta para ti.';
/** The turn that follows a «preguntar al agente» click: it reads the note the click left. */
export const NOTE_REPLY = 'Leí tu nota:';
/** The Local models of the fake daemon; the first is active. */
export const MODELS = [{ id: 'modelo-a', context_window: 32768 }, { id: 'modelo-b', context_window: 65536 }];
