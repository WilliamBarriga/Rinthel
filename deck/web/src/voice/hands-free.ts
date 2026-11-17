import { SpeechPipeline, type PreparedSpeech } from "./speech-pipeline";
import type { TranscriptItem as Item } from "../chat/model/transcript";
import { StreamingSpeech } from "./speech-text";
import { systemTimer, type Timer } from "../ports/timer";
import { displayPhase, holdsOutput, idleTurn, turnAfter, type TurnEvent, type TurnState } from "./model/hands-free-turn";

export const THINKING_PHRASES = [
  "Let me think about that for a moment.",
  "Give me a moment to think this through.",
  "Let me consider that.",
  "I’m thinking through your request.",
  "Let me take a moment with that.",
];

export const COMPACTION_PHRASES = [
  "My context is getting full. Let me quickly compact our conversation before I continue.",
  "I need a little room in my context. Let me summarize our conversation, then I'll carry on.",
  "Let me do a quick context compaction so I can keep going.",
];
export type VoicePhase = "Escuchando" | "Te escucho" | "Transcribiendo" | "Pensando" | "Compactando el contexto" | "Hablando";
export interface VoiceIO {
  sequential?: boolean;
  sentenceChunks?: boolean;
  ttsPrefetch?: boolean;
  statusSpeech?: boolean;
  transcribe: (samples: Float32Array, signal: AbortSignal) => Promise<string>;
  send: (text: string) => Promise<void>;
  abort: () => Promise<void>;
  agentRunning: () => boolean;
  synthesize: (text: string, signal: AbortSignal, kind?:'reply'|'status') => Promise<PreparedSpeech>;
  trace?: (name:string)=>void;
  phase: (phase: VoicePhase) => void;
  error: (message: string) => void;
  /** Time and chance come in, so a test drives the cues without waiting or luck. */
  timer?: Timer;
  random?: () => number;
}

/** Coordinates microphone turns independently of React renders and network timing. */
export class HandsFreeVoice {
  private turn: TurnState = idleTurn;
  private muted = false;
  private inputGeneration = 0;
  private acceptingReplies = true;
  private items: Item[] = [];
  private speech: StreamingSpeech;
  private recordings: Float32Array[] = [];
  private text: string[] = [];
  private output: string[] = [];
  private pipeline: SpeechPipeline;
  private thinkingPipeline: SpeechPipeline;
  private lastCompactionWaitAt = -Infinity;
  private transcription = new AbortController();
  private operations: Promise<void> = Promise.resolve();
  private timer: Timer;
  private random: () => number;
  private cancelThinking?: () => void;
  private thinkingAnnounced = false;
  private lastThinkingAt = -Infinity;
  private lastThinkingPhrase = -1;
  private clearThinkingTimer() { this.cancelThinking?.(); this.cancelThinking = undefined; }
  private get alive() { return this.turn.life === "alive"; }
  private get hearing() { return this.turn.input === "hearing"; }
  private get compacting() { return this.turn.compacting; }
  private get sending() { return this.turn.work === "sending"; }
  private apply(event: TurnEvent) { this.turn = turnAfter(this.turn, event); }
  /** The one condition under which replies wait for the agent to finish. */
  private holdsOutput() { return holdsOutput(this.io, this.io.agentRunning()); }


  constructor(private io: VoiceIO, initial: Item[]) {
    this.timer = io.timer ?? systemTimer;
    this.random = io.random ?? Math.random;
    this.pipeline = new SpeechPipeline(io.synthesize, () => this.state(), error => this.report(error), io.sequential, io.sentenceChunks, io.ttsPrefetch);
    this.thinkingPipeline = new SpeechPipeline(io.synthesize, () => this.state(), error => this.report(error));
    this.speech = new StreamingSpeech();
    this.items = initial;
    this.ignoreCurrent();
    io.phase("Escuchando");
  }
  private ignoreCurrent() {
    this.speech.ignore(this.items);
  }
  private report(error: unknown) {
    if (this.alive) this.io.error(error instanceof Error ? error.message : String(error));
  }
  private state() {
    if (!this.alive) return;
    const phase = displayPhase(this.turn, { speaking: this.pipeline.busy || this.thinkingPipeline.busy, agentRunning: this.io.agentRunning() });
    this.io.phase(phase);
    if (this.io.statusSpeech === false || this.io.sequential || phase !== "Pensando" || !this.acceptingReplies || this.output.length) this.clearThinkingTimer();
    else if (!this.thinkingAnnounced && !this.cancelThinking && this.timer.now() - this.lastThinkingAt >= 20000) {
      this.cancelThinking = this.timer.after(1800, () => {
        this.cancelThinking = undefined;
        if (!this.alive || this.compacting || this.hearing || !this.acceptingReplies || this.pipeline.busy || this.output.length || !(this.io.agentRunning() || this.sending)) return;
        this.thinkingAnnounced = true; this.lastThinkingAt = this.timer.now();
        const candidates = THINKING_PHRASES.map((_, i) => i).filter(i => i !== this.lastThinkingPhrase);
        this.lastThinkingPhrase = candidates[Math.floor(this.random() * candidates.length)];
        this.thinkingPipeline.enqueue([THINKING_PHRASES[this.lastThinkingPhrase]],'status');
      });
    }
  }
  setCompacting(active: boolean, completed = true) {
    if (!this.alive || active === this.compacting) return;
    this.apply({ type: "compacting", active });
    this.clearThinkingTimer();
    if (this.io.statusSpeech === false || this.io.sequential) { this.state(); return; }
    if (active) {
      this.lastCompactionWaitAt = -Infinity;
      this.thinkingPipeline.cancel();
      if (!this.hearing && this.acceptingReplies) this.pipeline.enqueue([COMPACTION_PHRASES[Math.floor(this.random() * COMPACTION_PHRASES.length)]],'status');
    } else this.pipeline.enqueue([completed ? "Context compaction is done. I'm ready to continue." : "Context compaction stopped before it finished."],'status');
    this.state();
  }
  observe(items: Item[]) {
    this.items = items;
    if (!this.alive) return;
    if (!this.acceptingReplies) this.ignoreCurrent();
    else if (!this.holdsOutput()) this.output.push(...this.speech.observe(items));
    this.state();
    void this.play();
  }
  /** Called after a sustained speech detection, not a single noise frame. */
  speechStart() {
    if (!this.alive || this.muted) return;
    const overCompaction = this.compacting;
    this.apply({ type: "speech-start" });
    if (overCompaction) {
      if (this.io.statusSpeech !== false && !this.io.sequential && this.timer.now() - this.lastCompactionWaitAt >= 8000) {
        this.lastCompactionWaitAt = this.timer.now();
        this.pipeline.enqueue(["I'm still compacting our conversation. Please wait a moment; I'll let you know when I'm ready."],'status');
      }
      return;
    }
    this.clearThinkingTimer();
    this.acceptingReplies = false;
    this.ignoreCurrent();
    this.output = [];
    this.pipeline.cancel();
    this.thinkingPipeline.cancel();
    // Serialize abort behind an in-flight send so it cannot miss that new run.
    if (this.io.agentRunning() || this.sending) {
      this.operations = this.operations.then(async () => { if (this.alive) await this.io.abort(); });
      void this.operations.catch(error => this.report(error));
    }
    this.state();
  }
  speechEnd(samples: Float32Array) {
    if (!this.alive || this.muted) return;
    this.apply({ type: "speech-end" });
    if (!this.turn.takesTurn) return;
    this.recordings.push(samples);
    void this.process();
  }
  private async process() {
    if (this.turn.work !== "idle" || !this.alive) return;
    const generation = this.inputGeneration;
    const valid = () => this.alive && this.inputGeneration === generation;
    this.apply({ type: "transcribe-start" });
    this.state();
    try {
      while (this.recordings.length && valid()) {
        const text = await this.io.transcribe(this.recordings.shift()!, this.transcription.signal);
        if (!valid()) return;
        if (text.trim()) this.text.push(text.trim());
      }
      // If speech resumes during transcription, retain the text and combine it
      // with the next segment instead of sending half a thought or losing it.
      if (this.hearing || !this.text.length) return;
      const text = this.text.join(" ");
      const send = this.operations.then(async () => {
        if (!valid() || this.hearing || this.recordings.length) return;
        this.ignoreCurrent();
        this.acceptingReplies = true;
        this.apply({ type: "send-start" });
        this.thinkingAnnounced = false;
        this.state();
        try {
          await this.io.send(text);
          if (valid()) this.text = [];
        } catch (error) {
          this.acceptingReplies = false;
          throw new Error(`Could not send “${text}”: ${error instanceof Error ? error.message : error}`);
        } finally { this.apply({ type: "send-end" }); }
      });
      this.operations = send;
      await send;
    } catch (error) {
      if (valid()) this.report(error);
      // A failed command is reported, but must not poison subsequent turns.
      this.operations = Promise.resolve();
    } finally {
      this.apply({ type: "transcribe-end" });
      this.state();
      if (this.alive && this.recordings.length) void this.process();
      else void this.play();
    }
  }
  private play() {
    if (!this.alive || this.hearing || !this.acceptingReplies || !this.output.length || this.holdsOutput()) return;
    const text = this.output; this.output = [];
    this.thinkingPipeline.cancel();
    this.io.trace?.('reply_chunk');
    this.pipeline.enqueue(text);
  }
  /** Mute is input-only: keep the agent and its spoken output running. */
  setMuted(muted: boolean) {
    this.muted = muted;
    if (muted) {
      this.inputGeneration++;
      this.apply({ type: "mute" });
      this.recordings = [];
      this.text = [];
      this.transcription.abort();
      this.transcription = new AbortController();
      this.acceptingReplies = true;
    }
    this.state();
    void this.play();
  }
  stop() {
    this.apply({ type: "stop" });
    this.clearThinkingTimer();
    this.pipeline.cancel();
    this.thinkingPipeline.cancel();
    this.transcription.abort();
    this.output = [];
    this.recordings = [];
    this.text = [];
  }
}
