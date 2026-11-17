# AGENTS.md: rinthel (daemon, client, hostexecd)

The repo-wide rules (graphify, Windows runtime, diagrams) are in the root
[`AGENTS.md`](../AGENTS.md). This file adds what is specific to `rinthel/`.

## Language

Code, comments, docstrings and commit messages in English. Text the TUI shows
the admin (phase labels, report lines, warnings) stays in Spanish, and tests
match it. Glossary definitions in [`GLOSSARY.md`](GLOSSARY.md) are in Spanish;
each term keeps its name.

## Structure rules

- Ports and adapters: a `domain/` never imports infrastructure, and only the
  composition (`lifecycle/composition.py`) looks at the operating system.
  `tests/import_table.py` is the table of allowed imports per module: a new
  module is a row there (or an entry in `UNGUARDED` with its reason).
- Every config is built from an explicit `Instance` and Platform
  (`default_config(instance, platform=...)`); tests use an Instance in
  `tmp_path`, never the repository's own `.env`.
- The `llama-server` argv and the Validated profile values are pinned by
  `tests/models/test_validated_profile.py`. Do not change them without a new
  benchmark on the reference hardware ([`docs/05-windows-validation.md`](../docs/05-windows-validation.md)).
- The protocol with the client is hand-written on both sides: a change to a
  daemon payload changes `tests/protocol_fixtures/` and
  `rinthel-client/src/protocol.rs` together.

## Tests

```bash
.venv/bin/python -m pytest -q                       # from rinthel/
(cd rinthel-client && cargo test --locked)          # when the client or a fixture changed
```

Never boot, install or terminate the real Instance from a test or a script;
the live tests (`-m live`) are opt-in and run by hand.
