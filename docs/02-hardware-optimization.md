# Hardware & Inference Tuning

Why the `llama-server` flags in `.env.example` are set the way they are.
They all stem from the same constraint: the model (35B total parameters,
~23 GB on disk quantized) doesn't fit entirely in the available VRAM.
Every flag on this list exists to squeeze out speed without crossing the
VRAM safety margin — these aren't arbitrary `llama.cpp` defaults, they're
the result of empirical tuning against this specific hardware.

Reference hardware: 8 GB VRAM NVIDIA GPU, 8 physical-core CPU, ~32 GB RAM.
If your GPU has more VRAM, most of this tuning (`--n-cpu-moe` especially)
can be relaxed — see each flag's section.

## The safety threshold: ~300 MiB of free VRAM

`--n-cpu-moe`, the expert cache, the batch sizes and the KV quantization
below are all knobs on the same trade: keep free VRAM above this floor
while pushing prefill speed. Values shown are the ones production runs
with (verified 2026-09-24).

The rule governing almost every decision below: under real load, at least
**~300 MiB of free VRAM** must be kept available. Below that, overflow
into shared memory over PCIe happens silently — no error in the log, just
a drop in tokens/second that looks like a problem somewhere else. Every
VRAM-touching flag below was measured against this floor.

This is a general floor, not the failure mode of quantizing only one of
`-ctk`/`-ctv` (see KV cache section below) — that mismatch runs out of
VRAM much faster and isn't a matter of tuning closer to a threshold.

## Model and quantization

**Qwen3.6-35B-A3B-MTP**, `UD-Q4_K_XL` quant (unsloth, 22.85 GB on disk).
MoE with 35B total parameters / 3B active per token, 256 experts, hybrid
architecture (Gated DeltaNet + attention — only 10 of 40 layers use
attention with a traditional KV cache, the rest is linear attention),
native context 262144. The `UD-Q4_K_XL` quant is what unsloth recommends
for setups with ~24 GB of combined VRAM+RAM; it's the point where the
model fits on this hardware without degrading output quality too much.

## `--n-cpu-moe 99` — GPU/CPU split for MoE experts

How many expert layers run on CPU instead of GPU (`99` = all of them;
the `config.py` default is 60). Lowering the number moves more compute to
GPU (faster prefill) but raises VRAM usage: on 8 GB, the real ceiling is
free VRAM under load, not compute speed. `99` is the value production
runs with the expert cache active (next section) and a `131072` context
without running out of memory — the cache is what keeps the hot experts
resident in VRAM even though every MoE layer is CPU-side. With more VRAM
available, lowering this number gains prefill speed.

## `RINTHEL_MTP_ENABLED` — MTP on/off with a single parameter

The gguf ships with MTP (multi-token prediction, speculative decoding)
baked in. One boolean turns it on and off — `true` → `--spec-type
draft-mtp` (mode from `RINTHEL_SPEC_TYPE`), `false` → `--spec-type
none`, regardless of what the mode variable says. Same checkbox in
`[N] CONFIGURAR > LLAMA-SERVER > SPECULATIVE DECODING`, so toggling it
never means editing `.env` by hand.

MTP is **off** in this setup (decision 2026-09-24): it needs ~650 MiB of
extra compute buffer for its CUDA graph capture (`test-tarkAIrk/logs/08`)
and at batch/ubatch 2048 the headroom freed by KV cache quantization is
already spent on the batch size — the retry in `test-tarkAIrk/logs/27`
bottomed out at 48 MiB free and died with `cudaMalloc failed: out of
memory`. It was briefly turned on (2026-09-22) and turned back off once
the trade was on the table: ~650 MiB-1 GB of VRAM for ~+6-7 `gen_tps`.
What to do if it is re-enabled and the server dies on the first real
request: lower `--ubatch-size`/`--batch-size` to `1024` or `512` from `[N]
CONFIGURAR > CÓMPUTO` (512 is the minimum-VRAM candidate with MTP — q8_0
leaves 1270-1370 MiB free there against the ~650 MiB MTP needs,
`test-tarkAIrk/handoff/04`), or flip the switch off again.

Two limitations of MTP in `llama.cpp`, independent of VRAM: it does not
support `--parallel` > 1, nor `--mmproj`. The config warns about the
first one and omits the second flag from the command while MTP is on
(the stored vision config is left untouched).

## Expert cache (`--moe-cache-profile` + `--moe-cache-slots 16`)

An MoE routing profile (which experts activate most often, captured ahead
of time by running the model under real load) used to keep those experts
preloaded and "hot" in VRAM instead of reloading them per request. On its
own, 16 slots gives **+121% prefill speed** (prompt tokens/s) over no
expert cache. `--moe-cache-slots` values above 16 (tried up to 32) don't
improve throughput further — the routing profile already covers the hot
set of experts at 16, more slots just spend VRAM on experts that are used
increasingly rarely. If something starts failing with `CUDA error: out of
memory` under normal use, this is the first suspect to lower, along with
raising `--n-cpu-moe`.

## KV cache quantization (`--cache-type-k q8_0` / `--cache-type-v q8_0`)

Quantizing the attention KV cache to `q8_0` frees VRAM with no measured
cost to `prompt_tps`, `gen_tps`, or task quality. **Always quantize `-k`
and `-v` together** — quantizing only one leaves free VRAM low enough
that overflow into shared memory over PCIe happens silently, well before
the general safety threshold above would otherwise apply.

## `--batch-size 2048` / `--ubatch-size 2048` — prefill batch size

The single largest driver of `prompt_tps` on this hardware — larger than
any effect from `--n-cpu-moe` or the expert cache profile. Raising it
keeps improving prefill speed at the cost of VRAM; `2048` is the largest
value that still clears the ~300 MiB safety threshold with the rest of
this config active **without MTP**. Going past it (3072) crosses the
threshold and is not usable.

This is the flag to lower first when MTP is enabled and the server runs
out of memory (see the MTP section above): 2048 leaves 706 MiB free, of
which MTP's compute buffer alone needs ~650 — nothing left for the rest
of the session.

## `-c 131072` — context window

The model's native context is 262144, but at that size it doesn't fit in
VRAM alongside the rest of this config. `131072` is the tested-stable
ceiling with the expert cache active — raising it without lowering
`--n-cpu-moe` or disabling the cache will hit the same OOM as the
threshold above.

## `--threads 8` / `--threads-batch 7`

Tuned for an 8-physical-core CPU: `--threads` uses all 8 for generation,
`--threads-batch` is kept at 7 during batched prefill so as not to
saturate the core that's also carrying the rest of the system (Docker
stacks, the TUI, etc.) while the model processes the prompt.

## `RINTHEL_SCHED_ASYNC_CPU` — async CPU scheduling (currently ON)

`true` (production value) leaves `llama.cpp`'s async CPU scheduling
enabled, so no `--no-sched-async-cpu` flag is passed at all. Its isolated
contribution to speed hasn't been precisely measured (it was ruled out as
the explanation for a separate VRAM gap between builds, but that doesn't
confirm or rule out an effect of its own). Don't flip it without
re-measuring before/after.

## If you have more than 8 GB of VRAM

Priority order for relaxing this tuning: raise `--batch-size`/
`--ubatch-size` past 2048 first (biggest prefill gain per MiB of VRAM
spent), then lower `--n-cpu-moe` (more layers to GPU) — and if MTP
(`RINTHEL_MTP_ENABLED`) gets switched on, don't count its ~650 MiB as
available headroom when doing any of the above. Raising
`--moe-cache-slots` past 16 is not worth it regardless of available VRAM
— see the expert cache section above. Changing more than one flag at a
time makes it impossible to tell which one caused what if something
starts failing.
