/**
 * When an event happened, in epoch milliseconds.
 *
 * The store writes `created_at` as UTC `YYYY-MM-DD HH:MM:SS` with no zone marker, which JS parses
 * as local time — an hour or ten out, depending on where the portal runs. The
 * live path writes a real ISO string, so both shapes turn up in the same table.
 */
export function eventTime(createdAt: string | undefined): number | undefined {
  if (!createdAt) return undefined;
  const iso = /[Zz]|[+-]\d\d:?\d\d$/.test(createdAt)
    ? createdAt
    : createdAt.replace(" ", "T") + "Z";
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? undefined : ms;
}
