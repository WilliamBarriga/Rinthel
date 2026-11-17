# Hardware & Inference Tuning

This document holds both Validated profiles: Linux first, then
[Windows](#windows-validated-profile), whose measurements are recorded in the
[validation record](05-windows-validation.md). Do not apply one machine's
profile to another without a benchmark.

Rinthel runs a model that is larger than the reference NVIDIA GPU, so the
validated profile deliberately shares work between CUDA and the CPU. Treat a
profile as a complete set: changing several memory-sensitive values at once
makes failures and regressions impossible to attribute.

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

## `mtp` — MTP on/off per Local model

The gguf ships with MTP (multi-token prediction, speculative decoding)
baked in. The `mtp` boolean of the Local model's catalog entry turns it on
and off — `true` → `--spec-type draft-mtp` (mode from `RINTHEL_SPEC_TYPE`),
`false` → `--spec-type none`, regardless of what the mode variable says
(see [`local-models.md`](local-models.md); the old `RINTHEL_MTP_ENABLED`
is ignored).

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

## Expert cache (`--moe-cache-mib`, `RINTHEL_MOE_CACHE_MIB`)

Upstream llama.cpp can keep a GPU-side cache of the MoE experts that live
on the CPU (`--moe-cache-mib N`, default 0 = off). Rinthel leaves it off:
the old `--moe-cache-profile`/`--moe-cache-slots` flags (routing profile +
slot count) only existed in the `thecodacus/llama.cpp` `perf` fork, which
Rinthel no longer uses, and the earlier "+121% prefill" measurement was
taken with that fork. The cache costs VRAM that the batch buffers and KV
cache need, so if you enable it, raise it in steps and watch free VRAM
under real load. If something starts failing with `CUDA error: out of
memory`, set it back to 0 and/or raise `--n-cpu-moe`. Re-measure on your
hardware before relying on it.

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

## If you have more than 8 GB of VRAM

Priority order for relaxing this tuning: raise `--batch-size`/
`--ubatch-size` past 2048 first (biggest prefill gain per MiB of VRAM
spent), then lower `--n-cpu-moe` (more layers to GPU) — and if MTP
(`RINTHEL_MTP_ENABLED`) gets switched on, don't count its ~650 MiB as
available headroom when doing any of the above. Raising
`--moe-cache-mib` above 0 only after the previous steps — see the expert
cache section above. Changing more than one flag at a
time makes it impossible to tell which one caused what if something
starts failing.

## Windows Validated profile

Validated on 2026-09-20 with an AMD Ryzen 7 260, 31.31 GiB usable RAM and an
NVIDIA GeForce RTX 5070 Laptop GPU with 8151 MiB VRAM:

```dotenv
RINTHEL_N_CPU_MOE=34
RINTHEL_UBATCH_SIZE=2048
RINTHEL_BATCH_SIZE=2048
RINTHEL_SPEC_TYPE=none
RINTHEL_CACHE_TYPE_K=q8_0
RINTHEL_CACHE_TYPE_V=q8_0
RINTHEL_MOE_CACHE_MIB=0
```

plus a context window of 65,536 tokens. These values are no longer written
to `.env`: they live once in `rinthel_tui/config.py::VALIDATED_PROFILES`
(the context window in the default Local model INSTALL puts in the catalog),
pinned with the exact `llama-server` argv by
`rinthel/tests/models/test_validated_profile.py`.

The model is `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`: 22.85 GB decimal
(21.28 GiB), 35.5B total parameters, about 3B active parameters per token.
The configured context is 65,536 tokens; the longest observed live session in
this validation reached 15,526 total tokens, so the full window is configured
but not yet exhaustively load-tested.

### Why these values

#### CPU/GPU split

`RINTHEL_N_CPU_MOE=34` keeps enough expert work on the CPU for the model and
runtime buffers to fit in 8 GB VRAM. Lower values may be faster but consume
more VRAM. Raise or lower this value only with simultaneous VRAM and
tokens/second measurement.

#### Context and KV cache

`65536` leaves more memory headroom than the previous 112K/131K experiments.
Both KV cache sides use `q8_0`; quantizing only one side is not a supported
profile. The pair reduces memory consumption without a quality regression in
the grounded-response validation.

#### Batch sizes

`2048/2048` improved prompt processing and remained stable in the Windows
validation. Larger batches can increase prefill speed, but they compete with
the KV cache and CUDA compute buffers.

#### Speculative decoding and expert cache

MTP speculative decoding remains disabled because it previously reproduced a
CUDA out-of-memory failure on the 8 GB card. The MoE expert cache is also
disabled in the Windows profile: the controlled load test left only 551 MiB
free VRAM, which is insufficient headroom for another persistent cache.

### Measured operating envelope

During a controlled 420-token generation, the server produced 30.0 tokens/s.
CPU utilization averaged 59.5% and peaked at 74.5%; system RAM peaked at
29.57 GiB used; GPU utilization peaked at 81%; VRAM stayed at 7341 MiB used
with 551 MiB reported free. Temperature peaked at 58 C and GPU power at
45.04 W. The longer validation through the previous web portal averaged about 32.5 tokens/s.

The AMD XDNA NPU is present but is not part of this profile. The installed
`llama-server` is a CUDA build, and the current GGUF inference path uses the
NVIDIA GPU plus CPU. Do not count the NPU's advertised TOPS as additional CUDA
capacity.

### Tuning order

For a different machine, change one dimension per benchmark:

1. Preserve `q8_0/q8_0`, disabled MTP and disabled expert cache as the safe
   baseline.
2. Find a stable CPU/GPU split with at least 300 MiB free VRAM under load.
3. Tune batch and ubatch together.
4. Increase context only after a long-session test.
5. Test MTP or an expert cache last, separately, and retain the previous
   profile for rollback.

More RAM mainly increases operating headroom and permits larger contexts; it
does not automatically improve generation speed. More VRAM can reduce CPU
offload and is the more direct path to higher throughput.
