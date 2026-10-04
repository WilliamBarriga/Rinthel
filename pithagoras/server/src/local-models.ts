/** Host model catalogue; the portal secret never reaches the browser. */
export let modelSwitching = false;
export function setModelSwitching(value: boolean) { modelSwitching = value; }
export async function localModels(key?: string) {
  const base = process.env.RINTHEL_DAEMON_URL;
  if (!base) throw new Error("El selector local no está configurado");
  const response = await fetch(`${base}/local-models`, {
    method: key === undefined ? "GET" : "POST",
    headers: {"Content-Type": "application/json", "X-Rinthel-Portal": process.env.PORTAL_SECRET || ""},
    ...(key === undefined ? {} : {body: JSON.stringify({key})}),
    signal: AbortSignal.timeout(420_000),
  });
  const result = await response.json() as {error?: string; active: string | null; busy: boolean; models: {key: string; name: string; id: string; available: boolean}[]};
  if (!response.ok) throw new Error(result.error || "No se pudo cambiar el modelo");
  return result;
}
