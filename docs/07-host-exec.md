# Ejecución en el host: instalación y revisión

Esta funcionalidad corresponde al PR de host exec. Windows permanece en un
PR independiente; aquí no se cambian sus perfiles ni sus mediciones.

## Preparación

`hostexecd` and whoever calls it share one token, `RINTHEL_HOSTEXECD_TOKEN`,
in the root `.env`. INSTALL (`INSTANCE — token de host exec`) and
`rinthel-boot.sh`, before starting the daemons, both go through
`rinthel_tui.install.host_exec.prepare_host_exec(repo_root)`: it keeps an
existing token, adopts one exported in the shell, generates one only when
there is none, and stops without printing or rotating anything when the
`.env` and the shell disagree. Tokens and `.env` files are local and never
go into Git.

Without a token `hostexecd` fails closed: it authenticates nobody.

## Extension and Compose

The pi extensions in `extensions/` (`rinthel-host-exec`,
`rinthel-subagents`) and `compose/host-exec.override.yaml` are kept, but the
root compose no longer includes the override: no service of the Instance
loads them until host exec and `subagent` move into Deck as admin-only
tools.

## Estado de contaminación

In Deck, `SessionTaint` (`deck/server/src/pi/session-taint.ts`) holds the
classification and the rebuild. On untrusted content the Guard marks the
Session in `deck.db` (`session_taint` table), outside pi's session file.
When a Session's pi starts, it starts tainted and is rebuilt from that
mark, or from every entry of its pi file (results from before the mark
included, whatever branch is active).

The taint lasts for the whole Session: a relaunch, a restart of Deck or a
lost pi file keeps it. A new, clean Session keeps host exec. If the mark
cannot be written, the running Session stays blocked.

## Alcance de delegación

La delegación a subagentes vive en `extensions/rinthel-subagents/`; reemplaza
al motor experimental `rinthel-agents`, cuya implementación se conserva en el
commit `94e1a1d84b6e8e0deac43d3875d55f0509cc8c31`. Cada subagente corre en su
propia sesión, donde el Guard de la sesión padre no está cargado. Por eso la extensión
excluye `rinthel_host_exec`, la escritura a Understory y `ask_user_question`
de esas sesiones, y el guard sigue tratando como no confiables los resultados
de subagentes instaladas por otros paquetes.

## Validación

```bash
(cd rinthel && .venv/bin/python -m pytest -q)
(cd deck && npm test)
```

Las pruebas de instalación usan archivos temporales. La comprobación de
Compose usa `config --no-interpolate` y no arranca contenedores.
