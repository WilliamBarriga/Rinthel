import test from 'node:test';
import assert from 'node:assert/strict';
import { createMemoryStore } from '../server/src/store/memory/index.ts';
import { createCanvases } from '../server/src/canvases.ts';
import { CanvasTools, canvasWritePrefix } from '../server/src/pi/canvas-tools.ts';
// The canvases and the tools over them run on the in-memory store: no Postgres, no singleton.
const store=createMemoryStore();
const canvases=createCanvases(store);
const {readCanvas,listCanvases,persistCanvas,createCanvas}=canvases;
await store.sessions.create({id:'s1',title:'test',workspace:'/tmp',executor:'host'});
await store.sessions.create({id:'s2',title:'other',workspace:'/tmp',executor:'host'});
function setup(){const controller=new CanvasTools('s1',canvases);const tools:Record<string,any>={};controller.extension({registerTool:(t:any)=>tools[t.name]=t} as any);return {controller,tools};}
const value=(r:any)=>{assert.equal(r.content[0].type,'text');return JSON.parse(r.content[0].text)};
async function delta(controller:any,id:string,raw:string){controller.observe({type:'message_update',assistantMessageEvent:{type:'toolcall_delta',contentIndex:0,delta:raw,partial:{content:[{type:'toolCall',name:'canvas_write',id}]}}});await controller.idle();}
test('partial JSON decoder preserves escapes and does not invent incomplete Unicode',()=>{
 assert.deepEqual(canvasWritePrefix('{"canvas_id":"abc","revision":0,"operation":"replace","content":"hello\\nworld\\u26'),{canvas_id:'abc',revision:0,operation:'replace',content:'hello\nworld'});
 assert.equal(canvasWritePrefix('{"canvas_id":"abc') ,undefined);
 assert.equal(canvasWritePrefix('{"canvas_id":"abc","revision":0,"operation":"append","content":"quote: \\" yes')?.content,'quote: " yes');
});
test('streamed content is retained in memory before execution and survives interruption; appending does not duplicate',async()=>{
 const {controller,tools}=setup();const row=value(await tools.canvas_create.execute('create',{title:'Document'}));
 await delta(controller,'write',`{"canvas_id":"${row.id}","revision":0,"operation":"replace","content":"First`);
 assert.equal((await readCanvas('s1',row.id)).content,'First');assert.equal((await readCanvas('s1',row.id)).status,'writing');
 await delta(controller,'write',' line\\nSecond');await controller.interrupt();
 let saved=await readCanvas('s1',row.id);assert.equal(saved.content,'First line\nSecond');assert.equal(saved.status,'interrupted');assert.equal(saved.active_call,null);
 const args={canvas_id:row.id,revision:saved.revision,operation:'append',content:' paragraph.'};
 await delta(controller,'append',JSON.stringify(args));value(await tools.canvas_write.execute('append',args));
 assert.equal((await readCanvas('s1',row.id)).content,'First line\nSecond paragraph.');
});
test('the Agent writes without reading first, and a canvas row carries no read revision',async()=>{
 const {controller,tools}=setup();const row=value(await tools.canvas_create.execute('create',{title:'No read needed'}));
 assert.equal('agent_read_revision' in row,false);
 const args={canvas_id:row.id,revision:row.revision,operation:'replace',content:'Agent words'};
 value(await tools.canvas_write.execute('first',args));assert.equal((await readCanvas('s1',row.id)).content,'Agent words');
 const again=await readCanvas('s1',row.id);
 value(await tools.canvas_write.execute('second',{...args,revision:again.revision,operation:'append',content:' more'}));
 assert.equal((await readCanvas('s1',row.id)).content,'Agent words more');
 await controller.interrupt();
});
test('only the Agent writes: the domain has no human edit',()=>{
 assert.equal('editCanvas' in canvases,false);assert.equal('markCanvasRead' in canvases,false);
});
test('future revisions recover during streaming and execution, and stale or concurrent writes stay refused',async()=>{
 const {controller,tools}=setup();const row=value(await tools.canvas_create.execute('create',{title:'Future revision'}));
 const args={canvas_id:row.id,revision:100,operation:'replace',content:'First line'};
 await delta(controller,'future',`{"canvas_id":"${row.id}","revision":100,"operation":"replace","content":"First`);
 assert.equal((await readCanvas('s1',row.id)).content,'First');
 await assert.rejects(tools.canvas_write.execute('concurrent',args),/being written/);
 await delta(controller,'future',' line"}');
 const result=value(await tools.canvas_write.execute('future',args));
 assert.equal(result.revision,(await readCanvas('s1',row.id)).revision);
 assert.equal((await readCanvas('s1',row.id)).content,'First line');
 assert.equal((await readCanvas('s1',row.id)).active_call,null);
 await assert.rejects(tools.canvas_write.execute('stale',{...args,revision:0}),/current revision/);
 value(await tools.canvas_write.execute('direct',{...args,operation:'append',content:' again'}));
 assert.equal((await readCanvas('s1',row.id)).content,'First line again');
});
test('a canvas is markdown or ui, markdown by default, and keeps its kind when stored',async()=>{
 assert.equal((await createCanvas('s1','Text')).kind,'markdown');
 const ui=await createCanvas('s1','Interface','ui');assert.equal(ui.kind,'ui');
 await assert.rejects(createCanvas('s1','Page','html' as any),/kind/);
 await persistCanvas('s1',ui.id);
 assert.equal((await store.canvases.get('s1',ui.id))?.kind,'ui');
 assert.equal((await listCanvases('s1')).find(r=>r.id===ui.id)?.kind,'ui');
});
test('session scope and revision checks protect other documents and active writes',async()=>{
 const {controller,tools}=setup();const row=value(await tools.canvas_create.execute('create',{title:'Scoped'}));
 await assert.rejects(readCanvas('s2',row.id),/not found/);assert.equal((await listCanvases('s2')).length,0);
 await delta(controller,'write',`{"canvas_id":"${row.id}","revision":0,"operation":"replace","content":"draft`);
 await assert.rejects(canvases.deleteCanvas('s1',row.id,1),/being written/);
 controller.observe({type:'message_end',message:{stopReason:'aborted'}});await controller.idle();
 assert.equal((await readCanvas('s1',row.id)).status,'interrupted');
 const current=await readCanvas('s1',row.id);value(await tools.canvas_delete.execute('delete',{canvas_id:row.id,revision:current.revision}));await assert.rejects(readCanvas('s1',row.id),/not found/);
});
test('AI can continue its own edits, including in a resumed controller',async()=>{
 const {tools}=setup();const row=value(await tools.canvas_create.execute('create',{title:'Continue'}));
 const first=value(await tools.canvas_write.execute('one',{canvas_id:row.id,revision:0,operation:'replace',content:'One'}));
 const second=value(await tools.canvas_write.execute('two',{canvas_id:row.id,revision:first.revision,operation:'append',content:' two'}));
 const resumed=setup();value(await resumed.tools.canvas_write.execute('three',{canvas_id:row.id,revision:second.revision,operation:'append',content:' three'}));
 assert.equal((await readCanvas('s1',row.id)).content,'One two three');
});

test('installed agent runtime forwards canvas data and errors to the next model request',async()=>{
 const {runAgentLoop}=await import('@earendil-works/pi-agent-core');
 const {tools}=setup();const created=value(await tools.canvas_create.execute('create',{title:'Visible to model'}));
 let calls=0;
 const stream=async(_model:any,context:any)=>{
  calls++;
  if(calls===2){
   const results=context.messages.filter((m:any)=>m.role==='toolResult');
   const listed=results.find((m:any)=>m.toolName==='canvas_list');assert.equal(listed.isError,false);
   assert.ok(JSON.parse(listed.content[0].text).some((row:any)=>row.id===created.id&&row.title==='Visible to model'));
   const missing=results.find((m:any)=>m.toolName==='canvas_read');assert.equal(missing.isError,true);assert.match(missing.content[0].text,/Canvas not found/);
  }
  assert.ok(calls<=2);
  const message={role:'assistant',api:'openai-completions',provider:'test',model:'test',timestamp:Date.now(),usage:{input:0,output:0,totalTokens:0,cost:{input:0,output:0,total:0}},stopReason:calls===1?'toolUse':'stop',content:calls===1?[{type:'toolCall',id:'list',name:'canvas_list',arguments:{}},{type:'toolCall',id:'missing',name:'canvas_read',arguments:{canvas_id:'not-a-real-id'}}]:[{type:'text',text:'I can see the canvas.'}]};
  return {async *[Symbol.asyncIterator](){yield {type:'done',message};},result:async()=>message};
 };
 await runAgentLoop([{role:'user',content:'List canvases',timestamp:Date.now()}],{systemPrompt:'',messages:[],tools:Object.values(tools)},{model:{id:'test',provider:'test',api:'openai-completions'},convertToLlm:(messages:any)=>messages},()=>{},undefined,stream);
 assert.equal(calls,2);
});


test('temporary canvases never reach the database until stored, including mid-stream; future edits auto-save',async()=>{
 const {controller,tools}=setup();const row=value(await tools.canvas_create.execute('temp',{title:'Temporary'}));
 const stored=async()=>(await store.canvases.get('s1',row.id)) as any;
 assert.equal(row.persisted,false);assert.equal(await stored(),undefined);
 await delta(controller,'live',`{"canvas_id":"${row.id}","revision":0,"operation":"replace","content":"Draft`);
 assert.equal(await stored(),undefined);
 await assert.rejects(persistCanvas('s2',row.id),/not found/);
 const saved=await persistCanvas('s1',row.id);assert.equal(saved.persisted,true);assert.equal((await stored()).content,'Draft');
 assert.equal((await persistCanvas('s1',row.id)).id,row.id);assert.equal((await listCanvases('s1')).filter(r=>r.id===row.id).length,1);
 await delta(controller,'live',' continues');await controller.interrupt();
 assert.equal((await stored()).content,'Draft continues');assert.equal((await stored()).active_call,null);
 const current=await readCanvas('s1',row.id);
 const result=value(await tools.canvas_write.execute('later',{canvas_id:row.id,revision:current.revision,operation:'append',content:' and more'}));
 assert.equal(result.persisted,true);assert.equal((await stored()).content,'Draft continues and more');
});
