import type { InstanceSoul } from "@deck/contract";
import type { InstanceSoulApi } from "../instance-soul";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";

/** The `fetch` adapter only knows HTTP: URL, status and JSON body. */
export function fetchInstanceSoulApi(fetchImpl: FetchLike = globalFetch): InstanceSoulApi {
  return {
    read: () => requestJson<InstanceSoul>(fetchImpl, "/api/agent/instance-soul"),
    save: (content) => requestJson<InstanceSoul>(fetchImpl, "/api/agent/instance-soul", { method: "PUT", body: JSON.stringify({ content }) }),
  };
}
