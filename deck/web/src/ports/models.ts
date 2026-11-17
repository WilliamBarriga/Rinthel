import type { ActivateResult, ActiveLocalModel, ModelListing } from "@deck/contract";

/**
 * Port: the Local model of the Instance (`/api/models`). Every user reads which one the Sessions talk
 * to (`active`); only the admin lists the catalog and switches (a member is a `403`). A switch while
 * turns are in course, or while the daemon is busy, is a `409` `PortError` whose message says why and
 * whose `body.code` is `turns_in_flight` or `lifecycle_busy`.
 */
export interface ModelsApi {
  active(): Promise<ActiveLocalModel>;
  list(): Promise<ModelListing>;
  activate(id: string): Promise<ActivateResult>;
}
