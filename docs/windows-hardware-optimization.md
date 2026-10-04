# Hardware and inference tuning

Rinthel runs a model that is larger than the reference NVIDIA GPU, so the
validated profile deliberately shares work between CUDA and the CPU. Treat a
profile as a complete set: changing several memory-sensitive values at once
makes failures and regressions impossible to attribute.

## Validated Windows profile

Validated on 2026-09-20 with an AMD Ryzen 7 260, 31.31 GiB usable RAM and an
NVIDIA GeForce RTX 5070 Laptop GPU with 8151 MiB VRAM:

```dotenv
RINTHEL_CONTEXT_WINDOW=65536
RINTHEL_N_CPU_MOE=34
RINTHEL_UBATCH_SIZE=2048
RINTHEL_BATCH_SIZE=2048
RINTHEL_SPEC_TYPE=none
RINTHEL_SCHED_ASYNC_CPU=false
RINTHEL_CACHE_TYPE_K=q8_0
RINTHEL_CACHE_TYPE_V=q8_0
RINTHEL_MOE_CACHE_SLOTS=0
```

The model is `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`: 22.85 GB decimal
(21.28 GiB), 35.5B total parameters, about 3B active parameters per token.
The configured context is 65,536 tokens; the longest observed live session in
this validation reached 15,526 total tokens, so the full window is configured
but not yet exhaustively load-tested.

## Why these values

### CPU/GPU split

`RINTHEL_N_CPU_MOE=34` keeps enough expert work on the CPU for the model and
runtime buffers to fit in 8 GB VRAM. Lower values may be faster but consume
more VRAM. Raise or lower this value only with simultaneous VRAM and
tokens/second measurement.

### Context and KV cache

`65536` leaves more memory headroom than the previous 112K/131K experiments.
Both KV cache sides use `q8_0`; quantizing only one side is not a supported
profile. The pair reduces memory consumption without a quality regression in
the grounded-response validation.

### Batch sizes

`2048/2048` improved prompt processing and remained stable in the Windows
validation. Larger batches can increase prefill speed, but they compete with
the KV cache and CUDA compute buffers.

### Speculative decoding and expert cache

MTP speculative decoding remains disabled because it previously reproduced a
CUDA out-of-memory failure on the 8 GB card. The MoE expert cache is also
disabled in the Windows profile: the controlled load test left only 551 MiB
free VRAM, which is insufficient headroom for another persistent cache.

### CPU scheduling

Asynchronous CPU scheduling is disabled in the validated profile. Its isolated
performance contribution has not been measured, so changing it requires an
A/B benchmark rather than an assumption.

## Measured operating envelope

During a controlled 420-token generation, the server produced 30.0 tokens/s.
CPU utilization averaged 59.5% and peaked at 74.5%; system RAM peaked at
29.57 GiB used; GPU utilization peaked at 81%; VRAM stayed at 7341 MiB used
with 551 MiB reported free. Temperature peaked at 58 C and GPU power at
45.04 W. The longer Pithagoras validation averaged about 32.5 tokens/s.

The AMD XDNA NPU is present but is not part of this profile. The installed
`llama-server` is a CUDA build, and the current GGUF inference path uses the
NVIDIA GPU plus CPU. Do not count the NPU's advertised TOPS as additional CUDA
capacity.

## Tuning order

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
