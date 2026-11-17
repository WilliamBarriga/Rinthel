import type { InstanceSoul } from "@deck/contract";

/**
 * Port: the Instance SOUL (`/api/agent/instance-soul` of Node), the `SOUL.md` every member's Sessions
 * load. Anyone logged in reads it (`editable` says whether they may change it); only the admin
 * replaces it, and the server refuses anyone else with `http` 403. Failures reject with a
 * `PortError` (see `http-errors.ts`). Every call answers the SOUL as it is stored after it.
 */
export interface InstanceSoulApi {
  read(): Promise<InstanceSoul>;
  /** Replaces it; stored with one trailing newline. */
  save(content: string): Promise<InstanceSoul>;
}
