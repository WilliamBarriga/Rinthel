import { useCallback, useEffect, useRef, useState } from "react";
import type { BrowserStatus } from "@deck/contract";
import { useBrowserApi } from "../ports/context";
import { PortError } from "../ports/http-errors";

export interface BrowserPageOptions {
  /** Tells the root about a failed request, so a `401` leads to the login and a `502` to its notice. */
  onFailure?: (error: unknown) => void;
  /** How often the open screen asks again. */
  pollMs?: number;
  /** Whether Deck is a secure context (a frame is only one if every ancestor is). Defaults to the window's. */
  secure?: boolean;
  /** What the person typed to reach Deck, for the link straight to the browser's own HTTPS port. */
  hostname?: string;
}

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));
/** A caller Deck will not serve does not get better by asking again every few seconds. */
const final = (e: unknown) => e instanceof PortError && (e.kind === "unauthorized" || e.status === 403);

/**
 * Controller of the Browser screen (the Instance browser, with a profile that stays signed in). It
 * reads `status` again every `pollMs` while mounted, never after, and stops when Deck refuses the
 * caller: `forbidden` is true for anyone who is not admin and the screen shows nothing of the browser.
 * A failed read becomes `error` and a call to `onFailure`; the last status stays. Nothing throws into
 * a view.
 *
 * Each write runs and reads again, even after a refusal (a step may have got halfway); a refusal stays
 * in `error` until the next write. The allowlist is a draft: typing marks it `dirty`, and a read does
 * not overwrite it until `saveAllowlist` went through. `install` saves a typed password first, then
 * starts an installed browser or installs a missing one. `uiUrl` is built here: over plain HTTP the
 * frame cannot start, so it links straight to the browser's HTTPS port.
 */
export function useBrowserPage({ onFailure, pollMs = 8000, secure, hostname }: BrowserPageOptions = {}) {
  const api = useBrowserApi();
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [allowlist, setAllowlistText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [shown, setShown] = useState(false);
  const [password, setPassword] = useState("");
  const failure = useRef(onFailure);
  failure.current = onFailure;
  const live = useRef(true);
  const isDirty = useRef(false);
  isDirty.current = dirty;
  const reload = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    live.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      let again = true;
      try {
        const s = await api.status();
        if (!live.current) return;
        setStatus(s);
        setLoadError(null);
        setForbidden(false);
        if (!isDirty.current) setAllowlistText(s.allowlist);
      } catch (e) {
        failure.current?.(e);
        if (!live.current) return;
        if (e instanceof PortError && e.status === 403) setForbidden(true);
        else setLoadError(messageOf(e));
        again = !final(e);
      }
      if (live.current && again) {
        clearTimeout(timer);
        timer = setTimeout(() => void load(), pollMs);
      }
    };
    reload.current = async () => {
      clearTimeout(timer);
      await load();
    };
    void load();
    return () => {
      live.current = false;
      clearTimeout(timer);
    };
  }, [api, pollMs]);

  const act = useCallback(async (write: () => Promise<void>): Promise<boolean> => {
    setBusy(true);
    setActionError(null);
    let ok = true;
    try {
      await write();
    } catch (e) {
      ok = false;
      failure.current?.(e);
      if (live.current) setActionError(messageOf(e));
    }
    await reload.current();
    if (live.current) setBusy(false);
    return ok;
  }, []);

  const installed = status?.install.container === "running" || status?.install.container === "stopped";
  const external = status?.install.mode === "external";
  const needsPassword = Boolean(status) && status?.install.mode === "docker" && !status?.config.hasPassword;
  const isSecure = secure ?? window.isSecureContext;
  const host = hostname ?? window.location.hostname;

  return {
    status,
    error: actionError ?? loadError,
    forbidden,
    busy,
    embeddable: isSecure,
    uiUrl: isSecure ? "/browser-ui/" : `https://${host}:${status?.uiPort ?? ""}/`,
    shown,
    toggleShown: () => setShown((v) => !v),
    allowlist,
    dirty,
    setAllowlist(text: string) {
      setAllowlistText(text);
      setDirty(true);
    },
    saveAllowlist: () =>
      act(async () => {
        await api.setAllowlist(allowlist);
        setDirty(false);
        isDirty.current = false;
      }),
    installed,
    external,
    needsPassword,
    password,
    setPassword,
    canInstall: !busy && !external && !(needsPassword && !password.trim()),
    suggestPassword: () => act(async () => setPassword(await api.suggestPassword())),
    /** Starts an installed browser and installs a missing one, saving the typed password first. */
    install: () =>
      act(async () => {
        if (password.trim()) await api.setConfig({ password: password.trim() });
        await (status?.install.container === "stopped" ? api.start() : api.install());
        setPassword("");
      }),
    stop: () => act(() => api.stop()),
    remove: (forgetProfile = false) => act(() => api.remove(forgetProfile)),
  };
}
