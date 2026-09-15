# Diagramas de arquitectura

Los diagramas de este repo se escriben en una variante del DSL de
[Eraser](https://docs.eraser.io/docs/syntax) (`*.eraser`) y se compilan a
HTML interactivo con [Archify](https://github.com/tt-a1i/archify).

Para arrancar ya: [`QUICKSTART.md`](QUICKSTART.md). Para la sintaxis
completa del subset soportado: [`SYNTAX.md`](SYNTAX.md).

## Requisitos

- Node.js (para correr Archify) — ya en PATH en este host.
- El paquete de Archify en `~/archify-pkg` (fuera de este repo). Si no está:
  clonar/descomprimir ese paquete en el home del usuario; el path está
  hardcodeado en `_ir_builder.py::ARCHIFY_BIN`.
- Python stdlib únicamente — no hace falta `pip install` nada para compilar.

## Flujo de trabajo

```bash
# 1. Compilar el .eraser a JSON IR de Archify, validando geometría/labels
.venv/bin/python docs/diagrams/eraser_to_archify.py \
    docs/diagrams/rinthel-runtime.eraser \
    docs/diagrams/out/rinthel-runtime.architecture.json \
    --validate

# 2. Si validate no tira errores, renderizar a HTML autocontenido
node ~/archify-pkg/archify/bin/archify.mjs render architecture \
    docs/diagrams/out/rinthel-runtime.architecture.json \
    docs/diagrams/out/rinthel-runtime.html
```

Abrir el `.html` resultante en el navegador — es interactivo (zoom, hover,
leyenda) y se ve muy por encima de un PNG de Graphviz.

## Escribir un diagrama nuevo

Sintaxis base (subset de Eraser real):

```
title: Mi Diagrama
direction: right

Nodo A [icon: server]
Nodo B [icon: postgresql]

Grupo {
  Nodo C [icon: docker]
}

Nodo A > Nodo B: hace una query
Nodo A <> Nodo B: bidireccional
```

- `icon:` primero intenta matchear el catálogo de marcas reales de Archify
  (`node ~/archify-pkg/archify/bin/archify.mjs brands`) — si el nombre del
  nodo o el icono coincide con algo como `postgresql`, `docker`, `github`,
  `python`, `discord`, `telegram`, sale el logo real. Si no matchea, cae a
  una tabla chica de palabras genéricas (`mail`, `monitor`, `server`,
  `database`, `network`, `cloud`, `queue`...).
- `{ }` anida grupos (se traducen a `boundaries` de Archify, tipo región).
- `A > B`, `A < B`, `A <> B` son las tres formas de conexión. `<>` genera
  dos conexiones (Archify no tiene una sola flecha bidireccional nativa).

### Dos extensiones sobre el Eraser real

Archify necesita un `componentType` tipado
(frontend/backend/database/cloud/security/messagebus/external) para su
leyenda, algo que el Eraser real no tiene. Por eso:

- `Nodo [icon: x, type: database]` — fuerza el tipo cuando ni la marca ni el
  icono genérico lo infieren bien (ej: Slack no tiene logo en el catálogo
  bundleado — `Slack [icon: slack, type: external]`).
- `Nodo [icon: x, row: 0, col: 2]` — fija la celda del grid cuando el
  layering automático (rank por distancia topológica desde los edges) elige
  mal. Dejarlo afuera salvo que `--validate` se queje.
- Una conexión puede terminar en `{style: dashed, labelDy: -20}` — pasa
  directo a la conexión de Archify (`style` mapea a `variant`; también
  soporta `fromSide`, `toSide`, `route`, `labelDx`, `labelSegment`).

## Cuando `--validate` se queja

Archify no hace auto-layout real — coloca por grid (`row`/`col`) y rutea
automático, pero el ruteo/labels pueden pisarse con topologías densas
(columnas con muchos nodos apilados, conexiones que saltan varias columnas).
`--validate` tira diagnósticos exactos con la coordenada y el fix sugerido
(`labelDy +54` / `labelAt [x, y]` / etc.) — iterar así:

1. Ver qué conexión/nodo señala el diagnóstico (**ojo**: para conexiones
   con label default, a veces el label que se pisa con una caja es el de
   *otra* conexión que pasa cerca, no el de la conexión "obvia" — confirmar
   el par `from`/`to` exacto en el mensaje antes de tocar nada).
2. Si es un label pisando una caja: `{labelDy: N}` con el valor sugerido.
3. Si es una conexión cruzando un nodo ajeno: mover ese nodo con
   `row`/`col` explícito, o probar `{route: orthogonal-v}` /
   `{fromSide: ..., toSide: ...}`.
4. Repetir `--validate` hasta 0 errores. Los warnings (`composition
   standard: N warnings`) son opcionales, no bloquean.

## Archivos

```
docs/diagrams/
├── _ir_builder.py               # lógica compartida: dict -> IR de Archify
├── eraser_to_archify.py         # parser del DSL + CLI (el único entrypoint)
├── rinthel-runtime.eraser        # fuente: arquitectura en runtime
├── rinthel-install-sources.eraser # fuente: de dónde saca cosas INSTALL
├── examples/
│   └── mail-integration.eraser   # ejemplo de sintaxis, no es de Rinthel
└── out/                          # generado — *.architecture.json + *.html
```

`out/` se puede regenerar en cualquier momento con el flujo de arriba; se
versiona igual que se versionaban los PNGs antes, para que los links desde
`docs/01-system-overview.md` funcionen sin tener que correr nada.
