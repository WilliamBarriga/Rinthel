import { EventEmitter } from 'node:events';
import { nanoid } from 'nanoid';
import { validateCanvasSpec, type CanvasSpecIssue } from '@deck/canvas-catalog';
import { CANVAS_KINDS, type CanvasKind, type PortalStore } from './store/port.js';

export interface CanvasRow { id: string; session_id: string; kind: CanvasKind; title: string; content: string; revision: number; status: string; active_call: string | null; updated_at: string; persisted: boolean }
/** A spec the catalog refuses: the message lists every issue so the model can fix them all in one try. */
export class CanvasSpecError extends Error {
  constructor(readonly issues: CanvasSpecIssue[]) {
    super(`Invalid canvas spec, nothing was saved. Fix it and write again:\n${issues.map(i => `- ${[i.element&&`[${i.element}]`,i.path&&`(${i.path})`,i.message].filter(Boolean).join(' ')}`).join('\n')}`);
  }
}
/**
 * The document canvases of the Instance, over the store they are given. The drafts
 * (temporary canvases) and the event emitter live in the instance, so two
 * instances never share state; the composition root builds one.
 */
export function createCanvases(store: Pick<PortalStore, 'canvases' | 'sessions'>) {
  const canvasEvents = new EventEmitter();
  canvasEvents.setMaxListeners(0);
  // Temporary canvases survive tab reconnects, but never a server restart.
  const temporary = new Map<string, CanvasRow>();
  // Read-check-write on a canvas must not interleave now that the store is async.
  let turn: Promise<unknown> = Promise.resolve();
  function exclusive<T>(task: () => Promise<T>): Promise<T> { const run = turn.then(task); turn = run.catch(() => undefined); return run; }
  /** The saved shape of a canvas: everything but the in-memory `persisted` flag. */
  function toRecord({persisted,...record}: CanvasRow) { return record; }
  async function update(row: CanvasRow, patch: Partial<CanvasRow>): Promise<CanvasRow> {
    const next = {...row,...patch};
    if (next.persisted) {
      await store.canvases.update(toRecord(next));
    } else temporary.set(next.id,next);
    return next;
  }
  async function persistCanvas(session:string,id:string): Promise<CanvasRow> {
    return exclusive(async () => {
    const row=await readCanvas(session,id);
    if(row.persisted) return row;
    await store.canvases.insert(toRecord(row));
    temporary.delete(id);
    return notify({...row,persisted:true});
    });
  }
  async function listCanvases(session: string): Promise<CanvasRow[]> {
    const stored=await store.canvases.list(session);
    return [...stored.map(row=>({...row,persisted:true})),...Array.from(temporary.values()).filter(row=>row.session_id===session)].sort((a,b)=>b.updated_at.localeCompare(a.updated_at));
  }
  async function readCanvas(session: string, id: string): Promise<CanvasRow> {
    const draft=temporary.get(id);
    if(draft?.session_id===session) return {...draft};
    const row=await store.canvases.get(session,id);
    if(!row) throw new Error('Canvas not found in this session');
    return {...row,persisted:true};
  }
  async function focusCanvas(session:string,id:string) { const row=await readCanvas(session,id);canvasEvents.emit(session,{type:'focus',canvas:row});return row; }
  function notify(row: CanvasRow) { canvasEvents.emit(row.session_id, { type: 'update', canvas: row }); return row; }
  async function createCanvas(session: string, title: string, kind: CanvasKind = 'markdown'): Promise<CanvasRow> {
    if (!CANVAS_KINDS.includes(kind)) throw new Error('Canvas kind must be markdown or ui');
    if (!await store.sessions.get(session)) throw new Error('Session not found');
    if (!title.trim() || title.length > 200) throw new Error('Title must contain 1–200 characters');
    const id = nanoid();
    temporary.set(id,{id,session_id:session,kind,title:title.trim(),content:'',revision:0,status:'draft',active_call:null,updated_at:new Date().toISOString(),persisted:false});
    const row=await readCanvas(session,id);canvasEvents.emit(session,{type:'create',canvas:row});return row;
  }
  async function deleteCanvas(session: string,id: string,revision: number) {
    return exclusive(async () => {
    const row=await readCanvas(session,id);
    if(row.active_call || row.revision!==revision) throw new Error('Canvas changed or is being written. Reload before deleting.');
    if(row.persisted) await store.canvases.delete(session,id);
    else temporary.delete(id);
    canvasEvents.emit(session,{type:'delete',id});
    });
  }
  async function beginCanvasWrite(session: string,id: string,revision: number,call: string): Promise<CanvasRow> {
    return exclusive(async () => {
    const row=await readCanvas(session,id);
    // A future revision cannot describe an older document; recover from model guesses.
    // Keep stale revisions and concurrent writes protected below.
    revision=Math.min(revision,row.revision);
    if(row.active_call || row.revision!==revision) throw new Error('Canvas changed or is being written. Use its current revision.');
    await update(row,{active_call:call,status:'writing'});
    return notify(await readCanvas(session,id));
    });
  }
  /**
   * Saves the whole spec of a `ui` canvas in one step. The catalog validates it first; an invalid spec
   * throws and leaves the canvas as it was. The state is the model's own: the server has no data to add. There is no streaming: half a spec is not a spec.
   */
  async function writeCanvasSpec(session: string,id: string,revision: number,spec: unknown): Promise<CanvasRow> {
    return exclusive(async () => {
    const row=await readCanvas(session,id);
    if(row.kind!=='ui') throw new Error('Only a ui canvas takes a spec; write content to a markdown canvas');
    revision=Math.min(revision,row.revision);
    if(row.active_call || row.revision!==revision) throw new Error('Canvas changed or is being written. Use its current revision.');
    const checked=validateCanvasSpec(spec);
    if(!checked.ok) throw new CanvasSpecError(checked.issues);
    const content=JSON.stringify(checked.spec);
    if(content.length>1_000_000) throw new Error('Canvas exceeds one million characters');
    await update(row,{content,revision:row.revision+1,status:'saved',updated_at:new Date().toISOString()});
    return notify(await readCanvas(session,id));
    });
  }
  async function saveCanvasPrefix(session: string,id: string,call: string,content: string): Promise<CanvasRow> {
    return exclusive(async () => {
    if(content.length>1_000_000) throw new Error('Canvas exceeds one million characters');
    const row=await readCanvas(session,id);
    if(row.active_call!==call) throw new Error('Canvas write is no longer active');
    if(row.content===content) return row;
    await update(row,{content,revision:row.revision+1,updated_at:new Date().toISOString()});
    return notify(await readCanvas(session,id));
    });
  }
  async function finishCanvasWrite(session: string,id: string,call: string,interrupted: boolean) {
    return exclusive(async () => {
    const row=await readCanvas(session,id);
    if(row.active_call!==call) return;
    return notify(await update(row,{active_call:null,status:interrupted?'interrupted':'saved',updated_at:new Date().toISOString()}));
    });
  }
  return { events: canvasEvents, persistCanvas, listCanvases, readCanvas, focusCanvas, createCanvas, deleteCanvas, beginCanvasWrite, writeCanvasSpec, saveCanvasPrefix, finishCanvasWrite };
}
export type Canvases = ReturnType<typeof createCanvases>;
