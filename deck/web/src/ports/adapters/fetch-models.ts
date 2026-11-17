import type { ActivateResult, ActiveLocalModel, ModelListing } from "@deck/contract";
import { globalFetch, requestJson, type FetchLike } from "../http-errors";
import type { ModelsApi } from "../models";

export function fetchModelsApi(fetchImpl: FetchLike = globalFetch): ModelsApi {
  return {
    active: () => requestJson<ActiveLocalModel>(fetchImpl, "/api/models/llm"),
    list: () => requestJson<ModelListing>(fetchImpl, "/api/models"),
    activate: (id) => requestJson<ActivateResult>(fetchImpl, "/api/models/activate", { method: "POST", body: JSON.stringify({ id }) }),
    off: (capability) => requestJson<ActivateResult>(fetchImpl, "/api/models/off", { method: "POST", body: JSON.stringify({ capability }) }),
  };
}
