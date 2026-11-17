import type { Appearance, Branding, Personalization } from "@deck/contract";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";
import type { AppearanceApi } from "../appearance";

/** The `fetch` adapter only knows HTTP: URL, status and JSON body. */
export function fetchAppearanceApi(fetchImpl: FetchLike = globalFetch): AppearanceApi {
  return {
    appearance: () => requestJson<Appearance>(fetchImpl, "/api/appearance"),
    saveAppearance: (value) => requestJson<Personalization>(fetchImpl, "/api/appearance", { method: "PUT", body: JSON.stringify(value) }),
    saveBranding: (value) => requestJson<Branding>(fetchImpl, "/api/appearance/brand", { method: "PUT", body: JSON.stringify(value) }),
  };
}
