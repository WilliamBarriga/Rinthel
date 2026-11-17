import { useEffect, useRef, useState } from "react";
import type { SessionEvent } from "@deck/contract";
import { VoiceProfiler } from "./voice-profile";

/** An event of the Session as voice reads it: its payload is pi's, untyped. */
export type VoiceEvent = SessionEvent & { payload: any };

/** Voice latency profiler: its panel toggle and the marks read from tool events. */
export function useVoiceProfiling(toolEvents: VoiceEvent[]) {
  const [profileOpen,setProfileOpen]=useState(false);
  const profiling=useRef(false);profiling.current=profileOpen;
  const [,refreshProfile]=useState(0);
  const profiler=useRef<VoiceProfiler | undefined>(undefined);
  if(!profiler.current)profiler.current=new VoiceProfiler(()=>refreshProfile(n=>n+1));
  const eventSeq=useRef(0);eventSeq.current=toolEvents.reduce((n,e)=>Math.max(n,e.seq),0);
  const profileSeq=useRef(Infinity);
  const profileLiveSeen=useRef(new WeakSet<object>());
  const profileMark=(name:string)=>{if(profiling.current)profiler.current!.mark(name);};
  useEffect(()=>{
    if(!profiling.current)return;
    for(const event of toolEvents){
      if(event.seq < 0) { if(profileLiveSeen.current.has(event))continue; profileLiveSeen.current.add(event); }
      else { if(event.seq<=profileSeq.current)continue; profileSeq.current=event.seq; }
      const inner=event.payload?.assistantMessageEvent;
      if(event.type==='message_update'&&inner?.delta&&['text_delta','thinking_delta','toolcall_delta'].includes(inner.type))profileMark('first_model_token');
      if(event.type==='message_update'&&inner?.delta&&inner?.type==='text_delta')profileMark('first_text');
      if(event.type==='message_update'&&inner?.type==='thinking_delta')profileMark('first_thinking_token');
      if(event.type==='portal_prefill')profiler.current!.mark('prefill_progress',{total:event.payload?.total??0,processed:event.payload?.processed??0,cache:event.payload?.cache??0,timeMs:event.payload?.timeMs??0});
      if(['portal_prompt','compaction_start','compaction_end','tool_execution_start','tool_execution_end','agent_end'].includes(event.type))profileMark(event.type);
    }
  },[toolEvents]);
  const toggleProfile = () => {
    setProfileOpen(value => !value);
    if (profileOpen) profiler.current!.close("disabled");
  };
  const closeProfile = () => { setProfileOpen(false); profiler.current!.close("disabled"); };
  return { profileOpen, profiling, profiler, profileSeq, eventSeq, profileMark, toggleProfile, closeProfile };
}
