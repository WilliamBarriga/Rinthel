import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { Type } from 'typebox';
import { canvasCatalogPrompt } from '@deck/canvas-catalog';
import type { Canvases } from '../canvases.js';
import type { CanvasKind } from '../store/port.js';
import { toolLabel } from './tool-text.js';

/** Decode only complete JSON escape sequences; an unfinished escape stays pending. */
function stringPrefix(raw: string,start: number): {value:string;end:number;complete:boolean} {
  let value='',i=start+1;
  for(;i<raw.length;i++) {
    const c=raw[i];if(c==='"')return {value,end:i+1,complete:true};
    if(c==='\\') {
      const next=raw[i+1];if(!next)break;
      const size=next==='u'?6:2;if(i+size>raw.length)break;
      try{value+=JSON.parse('"'+raw.slice(i,i+size)+'"')}catch{break} i+=size-1;
    } else {if(c.charCodeAt(0)<32)break;value+=c;}
  }
  // Do not persist half of a Unicode surrogate pair.
  if(/[\uD800-\uDBFF]$/.test(value)) value=value.slice(0,-1);
  return {value,end:i,complete:false};
}
export function canvasWritePrefix(raw: string): Record<string,any> | undefined {
  let i=0;const args:Record<string,any>={}; const ws=()=>{while(/\s/.test(raw[i]??'')&&i<raw.length)i++};
  ws();if(raw[i++]!=='{')return;
  while(i<raw.length){ws();if(raw[i]!== '"')return;const key=stringPrefix(raw,i);if(!key.complete)return;i=key.end;ws();if(raw[i++]!==':')return;ws();
    if(raw[i]==='"'){const v=stringPrefix(raw,i);args[key.value]=v.value;i=v.end;
      if(key.value==='content')return args;
      if(!v.complete)return;
    }else{const n=/^\d+(?=\s*[,}])/.exec(raw.slice(i));if(!n)return;args[key.value]=Number(n[0]);i+=n[0].length;}
    ws();if(raw[i++]!==',')return;
  }
}
/** The tools the Agent has over Canvases: a member's closed profile lists exactly these (`MEMBER_TOOLS`). */
export const CANVAS_TOOLS: readonly string[]=['canvas_list','canvas_create','canvas_read','canvas_write','canvas_delete'];
type Write={id:string;base:string;revision:number;operation:string;content:string};
export class CanvasTools {
  private writes=new Map<string,Write>();
  private raw=new Map<string,string>();
  private errors=new Map<string,string>();
  /** Deltas and tool calls are applied strictly in the order they arrived. */
  private queue:Promise<unknown>=Promise.resolve();
  constructor(private session:string,private canvases:Canvases){}
  private enqueue<T>(task:()=>Promise<T>|T):Promise<T> {const run=this.queue.then(task);this.queue=run.catch(()=>undefined);return run;}
  /** Resolves once everything observed so far has been saved. */
  idle():Promise<void> {return this.queue.then(()=>undefined);}
  /** `kind` is passed by whoever already read the canvas (`canvas_write`); the streaming path has not, so it falls back to reading it. */
  private async apply(call:string,p:any,kind?:CanvasKind) {
    if(typeof p?.canvas_id!=='string'||!Number.isInteger(p.revision)||!['replace','append'].includes(p.operation)||typeof p.content!=='string')return;
    if(this.errors.has(call))throw new Error(this.errors.get(call));
    let write=this.writes.get(call);
    if(!write){
      if((kind??(await this.canvases.readCanvas(this.session,p.canvas_id)).kind)==='ui')throw new Error('A ui canvas is written with spec, not content');
      const row=await this.canvases.beginCanvasWrite(this.session,p.canvas_id,p.revision,call);write={id:row.id,base:row.content,revision:p.revision,operation:p.operation,content:''};this.writes.set(call,write);}
    if(write.id!==p.canvas_id||write.revision!==p.revision||write.operation!==p.operation)throw new Error('Write metadata changed mid-stream; partial draft retained');
    await this.canvases.saveCanvasPrefix(this.session,write.id,call,(write.operation==='append'?write.base:'')+p.content);
    write.content=p.content;
  }
  observe(event:any) {this.enqueue(()=>this.handle(event)).catch((e)=>console.error('[canvas] could not apply event:',e));}
  private async handle(event:any) {
    const inner=event.assistantMessageEvent;
    if(event.type==='message_update'&&inner?.type==='toolcall_delta') {
      const tool=inner.partial?.content?.[inner.contentIndex];
      if(tool?.name!=='canvas_write'||!tool.id)return;
      const raw=(this.raw.get(tool.id)??'')+inner.delta;this.raw.set(tool.id,raw);
      const p=canvasWritePrefix(raw);if(!p || !p.content)return;
      try{await this.apply(tool.id,p)}catch(e){this.errors.set(tool.id,(e as Error).message);await this.finish(tool.id,true);}
    }
    if(event.type==='tool_execution_end'&&event.isError)await this.finish(event.toolCallId,true);
    if(event.type==='agent_end'||event.type==='agent_settled'||event.type==='message_end'&&['aborted','error'].includes(event.message?.stopReason))await this.interruptNow();
  }
  private async finish(call:string,partial:boolean){const w=this.writes.get(call);if(w)await this.canvases.finishCanvasWrite(this.session,w.id,call,partial);this.writes.delete(call);this.raw.delete(call);}
  private async interruptNow(){for(const call of [...this.writes.keys()])await this.finish(call,true);this.raw.clear();this.errors.clear();}
  interrupt():Promise<void> {return this.enqueue(()=>this.interruptNow());}
  extension=(pi:ExtensionAPI)=>{
    // Every Canvas tool runs in this Session's queue and answers its result as JSON text.
    const register = (name: string, description: string, parameters: any, execute: (id: string, p: any) => any) =>
      pi.registerTool({
        name,
        label: toolLabel(name),
        description,
        parameters,
        execute: async (id: string, p: any) => {
          const result = await this.enqueue(() => execute(id, p));
          return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
        },
      });
    register('canvas_list','List this session’s temporary and stored document canvases.',Type.Object({}),async()=>(await this.canvases.listCanvases(this.session)).map(({content,active_call,...row})=>({...row,characters:content.length})));
    register('canvas_create','Create an empty temporary canvas visible in this session: kind markdown (a document, the default) or ui (an interface built from a closed catalog of components). It is kept in memory until the user chooses Store in the UI. Then use canvas_write to write its content.',Type.Object({title:Type.String(),kind:Type.Optional(Type.Union([Type.Literal('markdown'),Type.Literal('ui')]))}),async(_id,p)=>{const row=await this.canvases.createCanvas(this.session,p.title,p.kind);return row});
    register('canvas_read','Read a document canvas and its current revision, including partial writes retained after interruption. Use the exact canvas ID returned by canvas_list or canvas_create, not its title.',Type.Object({canvas_id:Type.String()}),async(_id,p)=>{return this.canvases.focusCanvas(this.session,p.canvas_id)});
    register('canvas_write','Write a canvas. Arguments MUST be ordered canvas_id, revision, operation, content or spec (last). Use the revision from create/read/your last write; no read is needed first. MARKDOWN canvas: pass content; replace rewrites the document, append adds text; decoded content is saved as it streams, even if interrupted. UI canvas: pass spec, the COMPLETE spec every time with operation replace; it is validated against the catalog and, if invalid, you get the errors back and nothing is saved, so fix it and write again. Put the data the interface shows in the state of the spec; what the person types lives there too (bind fields with $bindState). A button can only change that state or leave you a message with askAgent.\n'+canvasCatalogPrompt(),Type.Object({canvas_id:Type.String(),revision:Type.Integer(),operation:Type.Union([Type.Literal('replace'),Type.Literal('append')]),content:Type.Optional(Type.String()),spec:Type.Optional(Type.Any())}),async(id,p)=>{
      const kind=(await this.canvases.readCanvas(this.session,p.canvas_id)).kind;
      if(kind==='ui'){
        if(p.content!==undefined||p.spec===undefined)throw new Error('A ui canvas is written with spec (the complete spec), not content');
        if(p.operation!=='replace')throw new Error('A ui canvas only takes operation replace with the complete spec');
        const row=await this.canvases.writeCanvasSpec(this.session,p.canvas_id,p.revision,p.spec);
        return {id:row.id,revision:row.revision,characters:row.content.length,saved:row.persisted,persisted:row.persisted};
      }
      if(typeof p.content!=='string'||p.spec!==undefined)throw new Error('A markdown canvas is written with content (text), not spec');
      try {await this.apply(id,p,kind);const row=await this.canvases.readCanvas(this.session,p.canvas_id);await this.finish(id,false);return {id:row.id,revision:row.revision,characters:row.content.length,saved:row.persisted,persisted:row.persisted};}
      catch(e){await this.finish(id,true);throw e;}
    });
    register('canvas_delete','Delete a canvas from this session when requested. Use its current revision (canvas_list or canvas_read).',Type.Object({canvas_id:Type.String(),revision:Type.Integer()}),async(_id,p)=>{await this.canvases.deleteCanvas(this.session,p.canvas_id,p.revision);return {deleted:true}});
  };
}
