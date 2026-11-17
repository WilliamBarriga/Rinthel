import { useId, useState } from "react";

export function Login({ onSubmit, error }: { onSubmit: (username: string, password: string) => Promise<void>; error?: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const prefix = useId();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSubmit(username, password);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-20">
      <form onSubmit={submit} aria-label="Acceso a la instalación" aria-busy={busy} className="ui-card w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src="/logo-512.png" alt="" className="h-16 w-16 object-contain" draggable={false} />
          <h1 className="ui-title mt-3 text-fg">Rinthel.Ai</h1>
          <p className="mt-1 text-xs text-fg-subtle">
            Inicia sesión para continuar en tu espacio de trabajo.
          </p>
        </div>

        <label htmlFor={`${prefix}-username`} className="mb-1 block text-sm text-fg">Usuario</label>
        <input
          id={`${prefix}-username`}
          autoFocus
          type="text"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Usuario"
          className="mb-3 min-h-11 w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm text-fg outline-none transition placeholder:text-fg-faint focus:border-accent/50 focus:ring-4 focus:ring-accent/10"
        />
        <label htmlFor={`${prefix}-password`} className="mb-1 block text-sm text-fg">Contraseña</label>
        <input
          id={`${prefix}-password`}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña"
          className="min-h-11 w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm text-fg outline-none transition placeholder:text-fg-faint focus:border-accent/50 focus:ring-4 focus:ring-accent/10"
        />
        {error && <p role="alert" className="mt-2 break-words text-xs text-danger">{error}</p>}

        <button
          type="submit"
          disabled={busy || !username || !password}
          className="mt-3 min-h-11 w-full rounded-xl bg-accent px-3 py-2.5 text-sm font-medium text-accent-fg transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Verificando…" : "Iniciar sesión"}
        </button>
      </form>
    </div>
  );
}
