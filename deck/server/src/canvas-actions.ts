import { canvasActionParams } from '@deck/canvas-catalog';
import type { Canvases } from './canvases.js';

/**
 * `CanvasActions`: what a click on a `ui` canvas asks the server to do.
 *
 * One action leaves the browser, `askAgent`, validated by the catalog's own params: it leaves a
 * message in the Session for the Agent. It never starts a turn: the Agent reads it in the next
 * one, when the person decides to speak. `SessionNotes` has no way to start one, so a click
 * cannot. The other actions of the catalog (`setState`, `pushState`, `removeState`,
 * `validateForm`) are local to the browser and never come here.
 *
 * Port: `SessionNotes` (`storedSessionNotes`, `InMemorySessionNotes`).
 */

/** Where a canvas leaves a message for the Agent. Adding a note never starts a turn. */
export interface SessionNotes {
  add(sessionId: string, text: string): Promise<void>;
}

export type CanvasActionOutcome = { kind: 'asked' };

/** A refused action; `status` is the HTTP code the portal answers with. */
export class CanvasActionError extends Error {
  constructor(message: string, readonly status: 400 | 404) {
    super(message);
  }
}

export interface CanvasActionsDeps {
  canvases: Pick<Canvases, 'readCanvas'>;
  notes: SessionNotes;
}

export function createCanvasActions({ canvases, notes }: CanvasActionsDeps) {
  return {
    /** Runs one action of a canvas of the Session. The action is checked against the catalog first. */
    async perform(sessionId: string, canvasId: string, input: { action: unknown; params: unknown }): Promise<CanvasActionOutcome> {
      const checked = canvasActionParams(input.action, input.params);
      if (!checked.ok) throw new CanvasActionError(checked.message, 400);
      let canvas;
      try {
        canvas = await canvases.readCanvas(sessionId, canvasId);
      } catch {
        throw new CanvasActionError('Canvas not found in this session', 404);
      }
      if (canvas.kind !== 'ui') throw new CanvasActionError('Only a ui canvas takes actions', 400);
      const text = checked.params.message.trim();
      if (!text) throw new CanvasActionError('Acción askAgent: the message is empty', 400);
      await notes.add(sessionId, text);
      return { kind: 'asked' };
    },
  };
}
export type CanvasActions = ReturnType<typeof createCanvasActions>;

/** Notes the portal keeps in the Session's own store: delivered with the next turn, never starting one. */
export function storedSessionNotes(store: { sessions: { addNote(sessionId: string, text: string): Promise<void> } }): SessionNotes {
  return { add: (sessionId, text) => store.sessions.addNote(sessionId, text) };
}

/** Notes kept in a list. That a note starts no turn is proven on the stored adapter (`storedSessionNotes`), not here. */
export class InMemorySessionNotes implements SessionNotes {
  readonly notes: { sessionId: string; text: string }[] = [];
  async add(sessionId: string, text: string): Promise<void> {
    this.notes.push({ sessionId, text });
  }
}
