# Local models

A Local model is a GGUF the Instance can serve for a Capability (`llm` today;
`stt` and `tts` with voice). One `llama-server` runs the active `llm` model,
shared by every Session. The terms are in [`rinthel/GLOSSARY.md`](../rinthel/GLOSSARY.md).

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
| `gguf` | The model file (`~` allowed). |
| `mmproj` | Vision projector, or `null`. Omitted from the command while `mtp` is on. |
| `mtp` | Turns speculative decoding on (`--spec-type` from `RINTHEL_SPEC_TYPE`). |
| `context_window` | `-c` of `llama-server`; Deck reads it from the routing. |
| `reasoning_format` | One of `qwen-chat-template`, `chat-template`, `qwen`, `deepseek`. |
| `overrides` | Only `temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `spec_type`, `spec_draft_n_max`. |

Hardware parameters (GPU layers, batch, threads, MoE cache, KV cache) are not
per model: they belong to the Validated profile of the Platform, in one place
(`rinthel_tui/config.py::VALIDATED_PROFILES`), and an explicit `.env` value
still wins. The old `RINTHEL_LLAMA_MODEL_PATH`, `RINTHEL_CONTEXT_WINDOW`,
`RINTHEL_LLAMA_MMPROJ_*` and `RINTHEL_MTP_ENABLED` are ignored with a warning.

The daemon validates on every read: the GGUF exists and starts with the
`GGUF` magic, the `mmproj` exists, the fields have the right shape and the id
is not repeated. An invalid entry stays listed as not activable; the catalog
never fails because of one entry.

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
  `rinthel/.venv/bin/python -m rinthel_tui.models list` and
  `rinthel/.venv/bin/python -m rinthel_tui.models use <id>`. It refuses while
  `llama-server` still listens; the next BOOT starts the new model.
- **From the daemon**: `POST /models/activate {"id": "<id>"}` kills
  `llama-server`, spawns it with the new model and waits until it answers. If
  it does not come up, the previous model is restarted and stays active
  (`rolled_back`). It runs under the global lifecycle lock (409
  `lifecycle_busy` against BOOT, TERMINATE, RELOAD and INSTALL) and answers 409
  `turns_in_flight` while `llama-server` reports a slot generating.
  `GET /models` lists the catalog with what can be activated. Both are
  admin-only by decision; until identity lands they take the service secret.

## Routing for Deck

`GET /model-provider/routing` (service secret) gives, per Capability with a
runnable active model, where Deck talks to it directly:

```json
{"capabilities": {"llm": {"url": "http://127.0.0.1:8080", "model": "qwen3.6-35b-a3b",
  "context_window": 112000, "reasoning_format": "qwen-chat-template"}}}
```

The URL is built with `deck.host_address` (`RINTHEL_DECK_HOST_ADDRESS`;
`127.0.0.1` on Linux, `host.docker.internal` on Windows). Deck never rewrites it.

## The legacy portal

Until Deck replaces it, the portal chats against the active model through
the pi provider `local-llm`. INSTALL sets `PI_PROVIDER`, `PI_MODEL` and
`LLAMA_BASE_URL` in the portal `.env`; BOOT and every switch rewrite that
provider in the portal's `models.json` (other providers are kept). The
provider has a single model with a fixed id, so a switch never leaves a portal
Session naming a model pi does not know; its name and context window follow
the active model. The portal's model selector stays gone.
