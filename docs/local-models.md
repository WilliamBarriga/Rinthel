# Local models

A Local model is a model file the Instance can serve for a Capability: `llm`,
and with voice (opt-in, Linux only) `stt` and `tts`. One `llama-server` runs
the active `llm` model, shared by every Session; `whisper-server` runs the
active `stt` model and `audiocpp-server` the active `tts` model. The terms are
in [`rinthel/GLOSSARY.md`](../rinthel/GLOSSARY.md).

## The catalog

The admin declares Local models by hand in `models.local.json` at the
Instance root (never tracked). INSTALL writes it once with the default model
of the Validated profile, next to `models.local.example.json` (every field,
including `mmproj` and `overrides`), and never rewrites it.

```json
{
  "models": [
    {
      "id": "qwen3.6-35b-a3b",
      "name": "Qwen3.6 35B A3B",
      "capability": "llm",
      "gguf": "~/llama.cpp/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
      "mmproj": null,
      "mtp": false,
      "context_window": 112000,
      "reasoning_format": "qwen-chat-template",
      "overrides": {}
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `id` | Unique; what `instance.toml`, the CLI and the routing name. |
| `name` | Shown to the admin. |
| `capability` | `llm`, `stt` or `tts`. |
| `gguf` | The model file (`~` allowed): a GGUF, or the whisper.cpp `ggml` file for `stt`. |
| `mmproj` | Vision projector, or `null`. Omitted from the command while `mtp` is on. |
| `mtp` | Turns speculative decoding on (`--spec-type` from `RINTHEL_SPEC_TYPE`). |
| `context_window` | `-c` of `llama-server`; Deck reads it from the routing. Optional for `stt`/`tts`. |
| `voice` | `tts` only, optional: the reference WAV of the fixed voice the model speaks with. |
| `reasoning_format` | One of `qwen-chat-template`, `chat-template`, `qwen`, `deepseek`. |
| `overrides` | Only `temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `spec_type`, `spec_draft_n_max`. |

Hardware parameters (GPU layers, batch, threads, MoE cache, KV cache) are not
per model: they belong to the Validated profile of the Platform, in one place
(`rinthel_tui/config.py::VALIDATED_PROFILES`), and an explicit `.env` value
still wins. The old `RINTHEL_LLAMA_MODEL_PATH`, `RINTHEL_CONTEXT_WINDOW`,
`RINTHEL_LLAMA_MMPROJ_*` and `RINTHEL_MTP_ENABLED` are ignored with a warning.

The daemon validates on every read: the GGUF exists and starts with the
`GGUF` magic (an `stt` file only has to exist), the `mmproj` and the `voice`
exist, the fields have the right shape and the id is not repeated. An invalid
entry stays listed as not activable; the catalog never fails because of one
entry.

## The active model

The active model of each Capability lives in `data/instance.toml`:

```toml
[models]
llm = "qwen3.6-35b-a3b"
```

If the active id is unknown or its entry became invalid, the daemon warns at
startup (and in `GET /config` warnings) and BOOT leaves `llama-server` out
with that warning; the other services still start.

## Switching

- **Offline**, with the services stopped:
  `rinthel/.venv/bin/python -m rinthel_tui.models list`,
  `rinthel/.venv/bin/python -m rinthel_tui.models use <id>` and
  `rinthel/.venv/bin/python -m rinthel_tui.models off stt|tts`. They refuse
  while the Capability's service still listens; the next BOOT starts the new
  model (or leaves the voice service out).
- **From the daemon**: `POST /models/activate {"id": "<id>"}` kills
  `llama-server`, spawns it with the new model and waits until it answers. If
  it does not come up, the previous model is restarted and stays active
  (`rolled_back`). It runs under the global lifecycle lock (409
  `lifecycle_busy` against BOOT, TERMINATE, RELOAD and INSTALL) and answers 409
  `turns_in_flight` while `llama-server` reports a slot generating.
  `GET /models` lists the catalog with what can be activated. A voice model
  switches the same way (its own service, same lock and rollback, no
  `turns_in_flight`), and `POST /models/off {"capability": "stt"|"tts"}`
  stops the voice service and drops its key; if the port does not free, the
  key stays. All three are admin-only: they take an admin's Panel token (not
  the service secret).

## Voice

Voice is opt-in and Linux only: on Windows INSTALL skips it, `stt`/`tts`
cannot be activated, and the routing and the Monitor leave them out.

- **Services.** `whisper-server` (whisper.cpp, CPU, port `8178`) serves the
  active `stt` model; `audiocpp-server` (audio.cpp, CUDA, port `7860`) the
  active `tts` model with the entry's `voice` as default preset (the daemon
  writes its `data/audiocpp-server.json` on every start). Both listen on
  loopback. Without an active key the Capability is off and its service
  does not start; BOOT, TERMINATE and RELOAD include it while the key is set.
  Ports, binaries and threads are `RINTHEL_WHISPER_*` and `RINTHEL_AUDIOCPP_*`.
- **GPU.** No leases: the TTS model stays loaded while `tts` is active. If it
  does not fit next to the LLM, turn `tts` off.
- **INSTALL with voice.** `rinthel/.venv/bin/python -m rinthel_tui.install --voice`
  asks the running daemon for INSTALL plus a voice unit: whisper.cpp and
  audio.cpp at fixed commits, `ggml-base.bin` and the Spanish Pocket-TTS
  GGUF (checked by sha256) in `RINTHEL_MODELS_DIR`, the entries
  `whisper-base` and `pocket-tts-es` added to the catalog if missing, made
  active where the Capability has none, and both services restarted. It is
  repeatable: what exists is not rebuilt, and an entry or a choice of the admin
  is never overwritten. The same is `POST /install {"voice": true}`.

The routing then also carries `stt` and `tts` (same shape; the URL is the
voice service at `deck.host_address`), and the Monitor shows each active
voice Capability with the state of its service.

## Routing for Deck

`GET /model-provider/routing` (service secret) gives, per Capability with a
runnable active model, where Deck talks to it directly:

```json
{"capabilities": {"llm": {"url": "http://127.0.0.1:8080", "model": "qwen3.6-35b-a3b",
  "context_window": 112000, "reasoning_format": "qwen-chat-template"}}}
```

The URL is built with `deck.host_address` (`RINTHEL_DECK_HOST_ADDRESS`;
`127.0.0.1` on Linux, `host.docker.internal` on Windows). Deck never rewrites it.

Deck reads it on every call of a Session and goes straight to `llama-server`
(ADR 0008). Each Session's slot is restored before a call and saved after it,
in `data/deck/llama-slots`: `llama-server` starts with that
`--slot-save-path`, after the Validated profile flags. The admin switches from
Deck (composer and Ajustes); Deck itself answers 409 `turns_in_flight` while
one of its Sessions is generating, and a live Session moves to the new model on
its next call (`wrong_model`).
