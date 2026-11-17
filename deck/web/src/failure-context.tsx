import { createContext, useCallback, useContext, type ReactNode } from "react";
import { isUnauthorized } from "./ports/http-errors";

/** What the root does with a failed request: a `401` leads to the login, a `502` to its notice. */
export type ReportFailure = (error: unknown) => void;

const FailureContext = createContext<ReportFailure>(() => {});

/** Gives every screen under the authenticated root the way to report a failure without prop drilling. */
export function FailureProvider({ report, children }: { report: ReportFailure; children: ReactNode }) {
  return <FailureContext.Provider value={report}>{children}</FailureContext.Provider>;
}

export function useReportFailure(): ReportFailure {
  return useContext(FailureContext);
}

/**
 * For an action that shows its own refusal: only an expired session (`401`) also leaves for the
 * login; a `403`, `409` or `5xx` stays as the message of the screen, not the root's notice.
 */
export function useReportExpired(): ReportFailure {
  const report = useReportFailure();
  return useCallback((error: unknown) => { if (isUnauthorized(error)) report(error); }, [report]);
}
