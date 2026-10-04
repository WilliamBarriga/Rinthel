import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { DefaultResourceLoader } from '@earendil-works/pi-coding-agent';
import { hostExecExtensionPaths } from '../dist/pi/host-exec.js';

const agentDir=mkdtempSync(join(tmpdir(),'rinthel-host-exec-loader-'));
test.after(()=>rmSync(agentDir,{recursive:true,force:true}));

test('a clean Pi installation loads both mounted host-exec tools without user settings',async(t)=>{
 const previousPath=process.env.RINTHEL_HOST_EXEC_EXTENSION;
 const previousToken=process.env.RINTHEL_HOSTEXECD_TOKEN;
 t.after(()=>{
  if(previousPath===undefined) delete process.env.RINTHEL_HOST_EXEC_EXTENSION;
  else process.env.RINTHEL_HOST_EXEC_EXTENSION=previousPath;
  if(previousToken===undefined) delete process.env.RINTHEL_HOSTEXECD_TOKEN;
  else process.env.RINTHEL_HOSTEXECD_TOKEN=previousToken;
 });
 process.env.RINTHEL_HOST_EXEC_EXTENSION=fileURLToPath(new URL('../../../extensions/rinthel-host-exec/index.ts',import.meta.url));
 process.env.RINTHEL_HOSTEXECD_TOKEN='loader-test-token';
 const loader=new DefaultResourceLoader({cwd:agentDir,agentDir,additionalExtensionPaths:hostExecExtensionPaths(),noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true});
 await loader.reload();
 const loaded=loader.getExtensions();
 assert.deepEqual(loaded.errors,[]);
 const tools=loaded.extensions.flatMap(extension=>[...extension.tools.keys()]);
 assert.ok(tools.includes('rinthel_host_exec'));
 assert.ok(tools.includes('rinthel_host_exec_history'));
});

test('an absent token disables host exec without breaking the portal',()=>{
 const previous=process.env.RINTHEL_HOSTEXECD_TOKEN;
 delete process.env.RINTHEL_HOSTEXECD_TOKEN;
 try { assert.deepEqual(hostExecExtensionPaths(),[]); }
 finally { if(previous!==undefined) process.env.RINTHEL_HOSTEXECD_TOKEN=previous; }
});
