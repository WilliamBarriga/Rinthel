import { useEffect, useRef, useState } from "react";
import { LuCheck, LuSparkles } from "react-icons/lu";
import type { VoiceEvent } from "./use-voice-profiling";

type Action = { id: number; callId: string; label: string; detail: string; done: boolean; failed: boolean; side?: "left" | "right"; lane?: number };

function action(event: VoiceEvent): Action {
  const p = event.payload ?? {}, input = p.args ?? p.input ?? p.parameters ?? {};
  const name = String(p.toolName ?? p.name ?? "tool");
  let label = `Usando ${name.replace(/[_.]+/g, " ")}`;
  if (/bash|terminal|shell|exec/.test(name)) label = "Ejecutando un comando";
  else if (/browser|navigate/.test(name)) label = "Usando el navegador";
  else if (/search|grep|find/.test(name)) label = "Buscando";
  else if (/read/.test(name)) label = "Leyendo un archivo";
  else if (/canvas/.test(name)) label = "Escribiendo en un Canvas";
  else if (/write|edit|patch/.test(name)) label = "Actualizando un archivo";
  const detail = [input.description, input.command, input.cmd, input.url, input.path, input.file_path, input.query, input.title].find((v) => typeof v === "string") ?? "";
  return { id: event.seq, callId: String(p.toolCallId ?? ""), label, detail: detail.replace(/\s+/g, " ").slice(0, 100), done: false, failed: false };
}

/** The Agent's tool calls while voice mode is on: each floats in, says what it does, and goes. */
export function VoiceToolActivity({ events }: { events: VoiceEvent[] }) {
  const seen = useRef(new Set(events.map((e) => e)));
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const sequence = useRef(0);
  const [actions, setActions] = useState<Action[]>([]);
  useEffect(() => {
    const fresh = events.filter((e) => !seen.current.has(e));
    if (!fresh.length) return;
    for (const e of fresh) seen.current.add(e);
    const added = fresh.filter((e) => e.type === "tool_execution_start").map((event) => {
      const index = sequence.current++;
      return { ...action(event), id: index, side: index % 2 ? "right" as const : "left" as const, lane: Math.floor(index / 2) % 2 };
    });
    const ended = fresh.filter((e) => e.type === "tool_execution_end");
    if (added.length || ended.length) setActions((current) => [...current, ...added].slice(-4).map((item) => {
      const end = ended.find((e) => item.callId && e.payload?.toolCallId === item.callId);
      return end ? { ...item, done: true, failed: !!end.payload?.isError } : item;
    }));
    for (const item of added) {
      const timer = setTimeout(() => { timers.current.delete(timer); setActions((current) => current.filter((a) => a.id !== item.id)); }, 8000);
      timers.current.add(timer);
    }
  }, [events]);
  useEffect(() => () => { for (const timer of timers.current) clearTimeout(timer); }, []);
  return (
    <div className="voice-tool-activity" aria-label="Actividad de herramientas" aria-live="polite" aria-relevant="additions">
      {actions.map((item) => (
        <div key={item.id} className={`voice-tool-float flies-${item.side} flight-lane-${item.lane}`}>
          {item.done && !item.failed ? <LuCheck aria-hidden="true" /> : <LuSparkles aria-hidden="true" />}
          <div><span>{item.failed ? "La acción falló" : item.label}</span>{item.detail && <p>{item.detail}</p>}</div>
        </div>
      ))}
    </div>
  );
}
