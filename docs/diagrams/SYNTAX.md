# Sintaxis del DSL (`.eraser`)

Referencia completa del subset de [Eraser](https://docs.eraser.io/docs/syntax)
que entiende `eraser_to_archify.py`. Para el flujo de compilación/render ver
[`README.md`](README.md); para arrancar rápido, [`QUICKSTART.md`](QUICKSTART.md).

Esto **no es** el DSL completo de Eraser real — es un subset reducido pensado
para un solo `diagram_type`: `architecture`. No hay flowcharts, ER diagrams
ni sequence diagrams; todo se compila al IR de arquitectura de Archify.

## Comentarios

```
// esto es un comentario, se ignora hasta fin de línea
Nodo A [icon: server] // también al final de una línea
```

## Nodos

```
Nombre del Nodo [icon: server]
```

- El nombre puede tener espacios; se usa tal cual como label salvo que se
  pase `label:` explícito.
- El nombre se convierte en un id interno vía slugify (minúsculas,
  no-alfanuméricos → `_`). Si dos nombres distintos slugifican igual,
  colisionan — usar nombres que difieran en caracteres alfanuméricos.
- No hay escape string (`"..."`) para nombres con caracteres reservados
  como sí tiene el Eraser real — evitar `[`, `]`, `{`, `}`, `:`, `>`, `<`
  en el nombre del nodo.

## Grupos

```
Grupo Externo [icon: cloud] {
  Nodo A [icon: server]

  Subgrupo {
    Nodo B [icon: database]
  }
}
```

- `{ }` anida grupos libremente; se traducen a `boundaries` (tipo `region`)
  en el IR de Archify.
- Un grupo puede llevar sus propias `[ ]` (por ahora solo `label:` tiene
  efecto en un grupo — el resto de props de nodo no aplican a un grupo).
- Los nodos de un mismo grupo quedan contiguos en su columna del layout
  aunque no compartan edges directos entre sí.

## Propiedades (`[ ]`)

Van entre corchetes después del nombre, separadas por coma:
`clave: valor` o `clave: "valor con espacios"`.

| Propiedad | Aplica a | Efecto |
|---|---|---|
| `icon:` | nodo | ver [Iconos](#iconos) |
| `label:` | nodo, grupo | texto mostrado en vez del nombre |
| `type:` | nodo | fuerza `componentType` (ver [Iconos](#iconos)) |
| `row:`, `col:` | nodo | fija la celda del grid (los dos juntos, no por separado) |

`type:` acepta tanto el vocabulario propio (`client`, `process`, `server`,
`container`, `storage`, `network`, `channel`, `system`) como el enum nativo
de Archify (`frontend`, `backend`, `database`, `cloud`, `security`,
`messagebus`, `external`) — ambos se mapean a este último. Ver el mapeo
completo en `TYPE_MAP` (`_ir_builder.py`).

`row`/`col` son el escape hatch para cuando el auto-layering (rank por
distancia topológica desde los edges) elige mal — dejarlos afuera salvo
que `archify validate` se queje.

## Conexiones

```
A > B: label opcional
A < B: label opcional
A <> B: label opcional
A > B: label opcional {style: dashed, labelDy: -20}
```

Solo estos tres operadores (el Eraser real también tiene `-`, `--`,
`-->` — **no soportados** acá):

| Operador | Significado |
|---|---|
| `>` | flecha A → B |
| `<` | flecha B → A (se invierte al parsear) |
| `<>` | bidireccional — genera **dos** conexiones separadas en el IR (Archify no tiene flecha doble nativa) |

El label va después de `:`, hasta el `{` si hay atributos de edge.

### Atributos de edge (`{ }`)

Al final de la línea, pasan casi directo a la conexión de Archify:

| Atributo | Efecto |
|---|---|
| `style: dashed` / `style: dotted` | → `variant: dashed` (Archify no distingue dotted) |
| `fromSide`, `toSide` | lado de salida/entrada del nodo |
| `route` | p.ej. `orthogonal-v` para forzar ruteo |
| `labelDy`, `labelDx` | desplazar el label (px) cuando se pisa con una caja |
| `labelSegment` | qué segmento de la ruta lleva el label |
| `width` | ancho de línea |

`labelDy`/`labelDx`/`labelSegment`/`width` se castean a número
automáticamente. Cuando dos `A <> B` con label comparten el mismo par de
nodos, el compilador ya separa sus labels en Y automáticamente (no hace
falta `labelDy` manual para ese caso).

## Iconos

`icon:` intenta, en orden:

1. **Catálogo de marcas real de Archify** — `node ~/archify-pkg/archify/bin/archify.mjs brands`
   lista los ids disponibles (`postgresql`, `docker`, `github`, `python`,
   `discord`, `telegram`, etc.). Si el `icon:` o el nombre del nodo
   matchea un id/alias/título del catálogo, se usa el logo real y el
   `componentType` se infiere de la categoría de la marca.
2. **Tabla de keywords genéricos** (fallback si no matcheó ninguna marca):

   | Keyword | `componentType` |
   |---|---|
   | `mail`, `inbox`, `email`, `external`, `saas`, `chat` | `external` |
   | `monitor`, `desktop`, `laptop`, `user`, `client`, `browser` | `frontend` |
   | `server`, `api`, `function` | `backend` |
   | `database`, `db`, `storage` | `database` |
   | `network`, `router`, `firewall`, `vpn`, `lock`, `shield` | `security` |
   | `cloud` | `cloud` |
   | `queue`, `bus`, `kafka` | `messagebus` |

3. Si nada matchea: `componentType` cae a `backend` por default (o usar
   `type:` explícito).

Nodos sin marca real (p.ej. Slack, que no está en el catálogo bundleado)
necesitan `type:` explícito: `Slack [icon: slack, type: external]`.

## Dirección

```
direction: right   // default, no necesita transform
direction: down     // transpone rows/cols del layout, best-effort
```

No están soportados `direction: up` / `direction: left` del Eraser real.

## Estilo

```
colorMode: pastel
styleMode: shadow
```

Se leen pero **no tienen efecto** — Archify no tiene equivalente exacto a
`colorMode`/`styleMode` del Eraser real. El compilador imprime una nota por
stderr al ignorarlos. Para cambiar el look, elegir `meta.visual_preset` a
mano en el JSON de salida (`classic` / `signal-flow` / `blueprint` /
`editorial`).

`typeface:` del Eraser real tampoco está soportado.

## Qué no está soportado (vs. Eraser real)

- Operadores `-`, `--`, `-->` (línea sin flecha, punteada, punteada con
  flecha) — solo `>` / `<` / `<>`.
- Escape string para nombres de nodo con caracteres reservados.
- `direction: up` / `direction: left`.
- Legends configurables por DSL (Archify genera su leyenda sola, a partir
  de los `componentType` usados).
- Otros `diagram_type` de Eraser (flowchart, ER, sequence) — este pipeline
  solo emite `architecture`.
- `typeface:`.
