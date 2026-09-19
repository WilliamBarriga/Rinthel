# Bug: Skills no se detectan en Pithagoras (ej. `/wayfinder`)

## Problema

Cuando el usuario invoca una skill instalada como `/wayfinder` desde la interfaz de Pithagoras, pi no la reconoce como comando registrado. En vez de ejecutarla directamente, el modelo "razona" sobre si podría ser una skill, sin activarla de inmediato.

## Arquitectura relevante

```
Browser → SSE → Portal (Node.js) → SDK pi-coding-agent → Session → Model
                                              │
                                      DefaultResourceLoader
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                         extensions     skills         prompts/themes
```

### Cómo Pithagoras lanza pi (host mode)

1. `session-manager.ts` → `startClient()` → `executor.launch()` → `SdkPiClient.create()`
2. `sdk-client.ts` → crea `DefaultResourceLoader` con `agentDir: pi.getAgentDir()`
3. `resourceLoader.reload()` → auto-discovery de skills desde `{agentDir}/skills/`
4. `session.prompt(message)` → el modelo recibe el prompt con descripciones de skills

### Dónde viven las cosas dentro del contenedor

| Qué | Path |
|-----|------|
| Home del usuario | `/data/home` (HOME env var) |
| Agent dir de pi | `/data/home/.pi/agent` |
| Skills instaladas | `/data/home/.pi/agent/skills/` |
| Settings.json | `/data/home/.pi/agent/settings.json` |
| Workspaces | `/workspaces` (mount bind del host) |
| Data persistent | `/data` (mount bind: `../data/pithagoras:/data`) |

### Skills instaladas en el contenedor

- `codebase-design/SKILL.md`
- `domain-modeling/SKILL.md`
- `grill-me/SKILL.md`
- `research/SKILL.md`
- `wayfinder/SKILL.md` (tiene `disable-model-invocation: true`)

## El bug

### Ubicación

**Archivo:** `server/src/pi/sdk-client.ts`, línea ~130

```typescript
resourceLoader = new pi.DefaultResourceLoader({
    cwd: opts.cwd,                        // workspace path
    agentDir: pi.getAgentDir(),           // ← AQUÍ ESTÁ EL PROBLEMA
    additionalSkillPaths: [builtinSkills], // pithagoras/skills
    extensionFactories: [...],
});
```

### Causa raíz

`pi.getAgentDir()` resuelve el directorio del agente usando esta lógica (en `config.js` de pi):

```javascript
export function getAgentDir() {
    const envDir = process.env.PI_CODING_AGENT_DIR;  // ← variable de entorno
    if (envDir) return expandTildePath(envDir);
    return join(homedir(), ".pi", "agent");           // ← fallback a $HOME/.pi/agent
}
```

Pithagoras calcula el path en `pi-settings.ts`:

```typescript
export const piAgentDir = (): string =>
  process.env.PI_CODING_AGENT_DIR?.trim() ||
  path.join(process.env.HOME || "/data/home", ".pi", "agent");
```

Ambas deberían dar `/data/home/.pi/agent` dentro del contenedor (porque `HOME=/data/home`). **PERO** hay un riesgo de discrepancia:

1. El CLI (`rinthel_tui`) corre en el **host**, donde `$HOME=/home/tarkark`
2. Pithagoras corre en el **contenedor**, donde `HOME=/data/home`
3. Si `PI_CODING_AGENT_DIR` no está seteado consistentemente, o si `homedir()` resuelve diferente en algún contexto, `getAgentDir()` podría retornar un path incorrecto (ej. `/root/.pi/agent` que no existe)

### Qué pasa cuando la skill no se detecta

1. `resourceLoader.getSkills()` no incluye `wayfinder`
2. `getCommands()` en `sdk-client.ts` solo itera sobre skills cargadas → `/wayfinder` no aparece
3. El usuario escribe `/wayfinder` en el UI de Pithagoras
4. Pithagoras lo envía como mensaje normal a `session.prompt()`
5. El modelo recibe el texto pero no tiene `/wayfinder` en los comandos disponibles
6. El modelo "razona" sobre si podría ser una skill, en vez de ejecutarla

## Sesión de investigación (2026-01-19)

### Lo que se confirmó

1. **`HOME=/data/home`** está explícitamente en el Dockerfile (línea 86) → dentro del contenedor debería ser correcto.
2. **Los skills existen** en `/data/home/.pi/agent/skills/` con wayfinder, codebase-design, domain-modeling, grill-me, research.
3. **El package manager auto-descubre skills** desde `{agentDir}/skills/` a través de `addAutoDiscoveredResources()` en `package-manager.js`. Esta llamada es incondicional para user skills.
4. **`settings.json` no tiene key `skills`** → `globalSettings.skills` es `[]`, lo que significa que `isEnabledByOverrides` retorna `true` para todos los skills descubiertos (sin overrides).
5. **No hay `PI_CODING_AGENT_DIR`** ni en docker-compose.yml ni en `.env` → ambas funciones usan el fallback.

### Diferencia entre las dos funciones

| Función | Fallback |
|---------|----------|
| `pi.getAgentDir()` | `os.homedir()` → Node.js lee HOME o `/etc/passwd` |
| `piAgentDir()` | `process.env.HOME \|\| "/data/home"` → hardcoded |

`os.homedir()` puede comportarse distinto a leer `process.env.HOME` directamente dependiendo de la versión de Node y el sistema. Si por alguna razón `homedir()` no respeta HOME en este entorno, devolvería `/root` o `/home/node` y los skills no se encontrarían.

El fix de usar `piAgentDir()` es más seguro porque tiene un fallback hardcoded a `/data/home` que no depende del comportamiento de `os.homedir()`.

### No se pudo verificar en caliente

No se pudo ejecutar Node dentro del contenedor para comparar `os.homedir()` vs `process.env.HOME`. Se necesita que Tarkark ejecute:
```
docker exec pithagoras node -e "console.log('HOME:', process.env.HOME); console.log('homedir:', require('os').homedir())"
```

### Flujo actual de carga de skills en Pithagoras

1. `sdk-client.ts` crea `DefaultResourceLoader` con `agentDir: pi.getAgentDir()` y `additionalSkillPaths: [builtinSkills]`
2. `resourceLoader.reload()` llama a `packageManager.resolve()`
3. `resolve()` llama a `addAutoDiscoveredResources()` que escanea `{agentDir}/skills/` → encuentra wayfinder, etc.
4. `enabledSkills` se construyen desde los recursos habilitados del package manager
5. `skillPaths = mergePaths(cliEnabledSkills, enabledSkills, additionalSkillPaths)`
6. `updateSkillsFromPaths(skillPaths)` llama a `loadSkills({ skillPaths, includeDefaults: false })`
7. Los skills cargados quedan en `this.session.resourceLoader.skills`
8. `getCommands()` itera sobre `session.resourceLoader.getSkills().skills` → genera `skill:wayfinder`

### Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `server/src/pi/sdk-client.ts` | Reemplazar `pi.getAgentDir()` por `piAgentDir()` |
| `server/src/pi/sdk-client.ts` | Agregar import de `piAgentDir` desde `../pi-settings.js` |

## Solución

### Fix principal: usar `piAgentDir()` en vez de `pi.getAgentDir()`

En `server/src/pi/sdk-client.ts`, reemplazar:

```typescript
import { piAgentDir } from "../pi-settings.js";  // ← agregar import
// ...
resourceLoader = new pi.DefaultResourceLoader({
    cwd: opts.cwd,
    agentDir: pi.getAgentDir(),      // ← cambiar por:
    agentDir: piAgentDir(),          // ← usa la misma lógica que el portal
    additionalSkillPaths: [builtinSkills],
    extensionFactories: factories,
});
```

Esto asegura que Pithagoras use su propia función de cálculo de path, que es consistente con todo lo demás del portal.

### Fix secundario: persistencia de skills en el host

Las skills están dentro del contenedor en `/data/home/.pi/agent/skills/`. Este path vive en el volumen bind-mount `../data/pithagoras:/data`, pero las **skills** no están en los mounts explícitos del docker-compose.yml.

Los mounts de packages en docker-compose.yml son:
```yaml
- ${PI_AGENT_DIR}/npm/node_modules:/data/home/.pi/agent/npm/node_modules:ro
- ${PI_AGENT_DIR}/git/github.com/harms-haus/pi-processes:/data/home/.pi/agent/git/github.com/harms-haus/pi-processes:ro
```

Las skills **no** están en estos mounts. Si se crearon dentro del contenedor, sobrevivirían porque `/data` es bind-mount, pero no están documentadas como parte del deploy.

Opciones:
- Asegurar que las skills existan en el host en `../data/pithagoras/home/.pi/agent/skills/`
- O copiarlas en el Dockerfile como se hacen las builtin (`COPY skills skills`)

## Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `server/src/pi/sdk-client.ts` | Reemplazar `pi.getAgentDir()` por `piAgentDir()` |
| `server/src/pi/sdk-client.ts` | Agregar import de `piAgentDir` desde `../pi-settings.js` |

## Verificación post-fix

1. Iniciar Pithagoras ✅
2. Crear/abrir una sesión ✅
3. Llamar a `GET /api/skills` → verificar que `wayfinder` aparece en el listado ✅
4. Enviar `/skill:wayfinder` como mensaje → ✅ **funciona** como comando de skill
5. Enviar `/wayfinder` como mensaje → ❌ no funciona (no encuentra sin prefijo `skill:`)

## Estado actual

- **Fix del path de agentDir:** Aplicado y verificado. `piAgentDir()` en vez de `pi.getAgentDir()` en `sdk-client.ts`.
- **Invocación de skills:** `/skill:wayfinder` funciona correctamente (confirmado).
- **Pendiente:** `/wayfinder` sin prefijo `skill:` no funciona. Ver plan en `../plans/slash-command-discovery.md`.

## Bugs pendientes

1. **Skills no descubribles con `/name`:** El usuario debe escribir `/skill:wayfinder` en vez de `/wayfinder`. Ver plan.
2. **Menú de slash commands limitado:** Al escribir `/` solo se muestran 8 comandos (todos builtins). Skills nunca aparecen.
3. **Sin navegación por teclado:** El menú de slash commands no responde a flechas arriba/abajo ni Tab.
4. **Tipo `where` ausente en `PiCommand`:** Los comandos de skills/extensions no tienen `where`, causando que `c.where === "client"` sea siempre false.
