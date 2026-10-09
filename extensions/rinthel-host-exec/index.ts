/**
 * Rinthel Host Exec — ejecutar comandos de shell en el host real
 *
 * A diferencia de la tool `bash` (que corre dentro del contenedor
 * Pithagoras), esta extensión le habla a `hostexecd`, un daemon FastAPI
 * chico que corre en la máquina host (fuera de Docker) bindeado a
 * 127.0.0.1. Gracias a `network_mode: host` en
 * pithagoras/docker-compose.yml, 127.0.0.1 dentro del contenedor ya es el
 * loopback del host — no hace falta mount ni túnel para llegar a él.
 *
 * Ver plans/rinthel-host-exec.md para el diseño completo (grillado con
 * Tarkark, decisiones ya cerradas). Puntos clave:
 * - Sin allowlist de comandos: mismo nivel de libertad que `bash`, la
 *   restricción real es que el daemon corre como el usuario `tarkark`, sin
 *   sudo — cualquier cosa que necesite privilegios de root falla sola, a
 *   nivel de sistema operativo.
 * - Bloqueante, sin gestión de procesos de fondo: `POST /exec` espera a
 *   que el comando termine (con timeout) y devuelve stdout/stderr/exit
 *   code de una sola vez.
 * - `pithagoras/server/src/pi/guard.ts` bloquea el tool `rinthel_host_exec`
 *   por completo (sin excepciones de forma, a diferencia de las reglas
 *   puntuales que aplican a `bash`) cuando la sesión está "tainted" —
 *   leyó contenido no confiable.
 *
 * Nombres con prefijo `rinthel_` a propósito — a diferencia de `bash`/
 * `read`/etc. (built-ins de pi) o de otras extensiones instaladas
 * (`pi-processes`, ...), estas dos son custom nuestras: el prefijo las hace
 * reconocibles como tales apenas Rinthel lista sus tools disponibles.
 *
 * 2 tools expuestas:
 * - rinthel_host_exec(command, cwd?, timeout?) — corre un comando en el host
 * - rinthel_host_exec_history(limit?) — últimas ejecuciones auditadas por hostexecd
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// ─── Constants ───────────────────────────────────────────────────────────────

// Siguiente puerto libre tras 8765 (rinthel_tui)/3800 (Understory)/4100
// (Pithagoras) — mismo default que hostexecd/daemon.py::main().
const DEFAULT_PORT = 8766;
const TOKEN_HEADER = "X-Rinthel-Token";

interface ExecResponse {
	exit_code: number;
	stdout: string;
	stderr: string;
	duration_ms: number;
	timed_out: boolean;
}

interface HistoryEntry {
	ts: number;
	command: string;
	cwd: string | null;
	exit_code: number;
	duration_ms: number;
	stdout_len: number;
	stderr_len: number;
	timed_out: boolean;
}

function daemonBaseUrl(): string {
	const port = process.env.RINTHEL_HOSTEXECD_PORT?.trim() || String(DEFAULT_PORT);
	return `http://127.0.0.1:${port}`;
}

function daemonToken(): string | undefined {
	const token = process.env.RINTHEL_HOSTEXECD_TOKEN?.trim();
	return token || undefined;
}

const missingTokenText =
	"RINTHEL_HOSTEXECD_TOKEN no está seteado en el entorno de este contenedor — no se puede " +
	"autenticar contra hostexecd. Avisale a Tarkark, esto se configura en .env / docker-compose.yml.";

/** Mensaje legible para el modelo cuando el fetch mismo falla (daemon no
 * levantado en el host, DNS/conexión rechazada, etc.) — nunca una excepción
 * cruda hacia el caller. */
function unreachableText(err: unknown): string {
	const detail = err instanceof Error ? err.message : String(err);
	return (
		`No se pudo contactar a hostexecd en ${daemonBaseUrl()} (${detail}). El daemon se ` +
		"autostartea desde rinthel-boot.sh en el host — si Pithagoras se levantó sin pasar por " +
		"ese script (o el daemon se cayó), no va a estar arriba. Decile a Tarkark en vez de " +
		"reintentar en loop."
	);
}

function unauthorizedText(): string {
	return (
		"hostexecd rechazó el token (401) — RINTHEL_HOSTEXECD_TOKEN no matchea entre este " +
		"contenedor y el host. Requiere que alguien lo revise, no es algo para reintentar."
	);
}

function textResult(text: string) {
	return { content: [{ type: "text" as const, text }], details: {} };
}

// ─── Extension ───────────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "rinthel_host_exec",
		label: "Rinthel Host Exec",
		description:
			"Corre un comando de shell en la máquina host real (fuera del contenedor Pithagoras), " +
			"como el usuario tarkark, sin sudo. Bloqueante: espera a que el comando termine (con " +
			"timeout) y devuelve stdout/stderr/exit code. Sin allowlist de comandos — mismo nivel " +
			"de libertad que bash, pero corriendo en el host en vez del contenedor. Cualquier cosa " +
			"que necesite privilegios de root falla sola, a nivel de sistema operativo. Bloqueada " +
			"por completo si esta sesión leyó contenido no confiable.",
		parameters: Type.Object({
			command: Type.String({ description: "El comando de shell a correr en el host" }),
			cwd: Type.Optional(
				Type.String({ description: "Directorio de trabajo en el host (default: $HOME del host)" }),
			),
			timeout: Type.Optional(
				Type.Integer({ description: "Timeout en segundos, de 1 a 600 (default: el del daemon, 60s)" }),
			),
		}),
		execute: async (_toolCallId, params) => {
			const token = daemonToken();
			if (!token) return textResult(missingTokenText);

			const command = params.command as string;
			const cwd = (params.cwd as string | undefined) ?? null;
			const timeout = (params.timeout as number | undefined) ?? null;

			let res: Response;
			try {
				res = await fetch(`${daemonBaseUrl()}/exec`, {
					method: "POST",
					headers: { "Content-Type": "application/json", [TOKEN_HEADER]: token },
					body: JSON.stringify({ command, cwd, timeout }),
				});
			} catch (err) {
				return textResult(unreachableText(err));
			}

			if (res.status === 401) return textResult(unauthorizedText());
			if (!res.ok) {
				const body = await res.text().catch(() => "");
				return textResult(`hostexecd devolvió ${res.status}: ${body || "(sin cuerpo)"}`);
			}

			const data = (await res.json()) as ExecResponse;
			const header = data.timed_out
				? `⏱️ timeout tras ${data.duration_ms}ms (exit ${data.exit_code})`
				: `exit ${data.exit_code} (${data.duration_ms}ms)`;
			const parts = [header];
			if (data.stdout) parts.push(`stdout:\n${data.stdout}`);
			if (data.stderr) parts.push(`stderr:\n${data.stderr}`);

			return {
				content: [{ type: "text" as const, text: parts.join("\n\n") }],
				details: { exit_code: data.exit_code, timed_out: data.timed_out },
			};
		},
	});

	pi.registerTool({
		name: "rinthel_host_exec_history",
		label: "Rinthel Host Exec History",
		description:
			"Devuelve las últimas ejecuciones de rinthel_host_exec, auditadas por hostexecd " +
			"(logs/hostexecd.log en el host) — comando, exit code, duración, timestamp.",
		parameters: Type.Object({
			limit: Type.Optional(
				Type.Integer({ description: "Cuántas entradas devolver, más recientes primero (default: 20)" }),
			),
		}),
		execute: async (_toolCallId, params) => {
			const token = daemonToken();
			if (!token) return textResult(missingTokenText);

			const limit = (params.limit as number | undefined) ?? 20;

			let res: Response;
			try {
				res = await fetch(`${daemonBaseUrl()}/history?limit=${encodeURIComponent(String(limit))}`, {
					headers: { [TOKEN_HEADER]: token },
				});
			} catch (err) {
				return textResult(unreachableText(err));
			}

			if (res.status === 401) return textResult(unauthorizedText());
			if (!res.ok) {
				const body = await res.text().catch(() => "");
				return textResult(`hostexecd devolvió ${res.status}: ${body || "(sin cuerpo)"}`);
			}

			const data = (await res.json()) as { entries: HistoryEntry[] };
			if (!data.entries.length) return textResult("Sin ejecuciones registradas todavía.");

			const text = data.entries
				.map((e) => {
					const when = new Date(e.ts * 1000).toISOString();
					const flag = e.timed_out ? " TIMEOUT" : "";
					return `[${when}] exit ${e.exit_code}${flag} (${e.duration_ms}ms): ${e.command}`;
				})
				.join("\n");

			return textResult(text);
		},
	});
}
