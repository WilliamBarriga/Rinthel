import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { FailureProvider } from "./failure-context";
import { Login } from "./components/Login";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { useAuthSession } from "./auth/use-auth-session";
import { IsAdminContext } from "./auth/use-is-admin";
import { SessionsPage } from "./sessions/SessionsPage";
import { ChatPage } from "./chat/ChatPage";
import { SettingsPage } from "./settings/SettingsPage";
import { AppearanceProvider, AppearancePanel } from "./appearance/Appearance";
import { InstanceSoulPanel } from "./instance-soul/InstanceSoulPanel";
import { Sidebar } from "./shell/Sidebar";
import { UsersPage } from "./users/UsersPage";
import { VoicePage } from "./voice/VoicePage";
import { NAVIGATION, canVisit, destinationFor, type NavigationEntry } from "./navigation";

export default function App({ navigation = NAVIGATION }: { navigation?: readonly NavigationEntry[] }) {
  const { state, login, logout, retry, reportFailure } = useAuthSession();

  if (state.status === "checking") {
    return (
      <AccessPresentation><div role="status" className="flex min-h-dvh items-center justify-center text-sm text-fg-subtle">Cargando…</div></AccessPresentation>
    );
  }
  if (state.status === "unavailable" || state.status === "failed") {
    return (
      <AccessPresentation><div className="flex min-h-dvh items-center justify-center px-4 py-20"><section role="alert" className="ui-card flex w-full max-w-md flex-col items-center gap-3 text-center">
        <h1 className="ui-title text-fg">
          {state.status === "unavailable" ? "Servicio no disponible" : "No se pudo continuar"}
        </h1>
        <p className="w-full max-w-xs break-words text-xs text-fg-subtle">
          {state.status === "unavailable"
            ? "No se pudo conectar con el servicio. Vuelve a intentarlo en un momento."
            : state.message}
        </p>
        <button
          onClick={() => void retry()}
          className="min-h-11 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-accent-fg transition hover:opacity-90"
        >
          Reintentar
        </button>
      </section></div></AccessPresentation>
    );
  }
  if (state.status === "anonymous") {
    return (
      <AccessPresentation>
        <Login onSubmit={login} error={state.loginError} />
      </AccessPresentation>
    );
  }

  // The registry owns the rows; each slice owns its screen. `/users/:id` also covers `/users/new`.
  const usersPage = <UsersPage onFailure={reportFailure} username={state.username} />;
  const pages: Readonly<Record<string, ReactNode>> = {
    "/": <SessionsPage username={state.username} />,
    "/sessions/:id": <ChatPage />,
    "/soul": <InstanceSoulPanel />,
    "/appearance": <div className="px-5 py-5"><AppearancePanel /></div>,
    "/voice": <VoicePage />,
    "/settings": <SettingsPage />,
    "/users": usersPage,
    "/users/new": usersPage,
    "/users/:id": usersPage,
  };
  const shell = { isAdmin: state.isAdmin, username: state.username, navigation, onLogout: () => void logout() };

  return (
    <FailureProvider report={reportFailure}><IsAdminContext.Provider value={state.isAdmin}><AppearanceProvider key={state.username} isAdmin={state.isAdmin}>
      <RouteGuard isAdmin={state.isAdmin} navigation={navigation}>
        <Routes>
          {Object.entries(pages).map(([path, page]) => (
            <Route key={path} path={path} element={<Shell {...shell} view={destinationFor(path, navigation)?.id}>{page}</Shell>} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </RouteGuard>
    </AppearanceProvider></IsAdminContext.Provider></FailureProvider>
  );
}

function AccessPresentation({ children }: { children: ReactNode }) {
  return <><div className="fixed right-4 top-4 z-10"><ThemeSwitcher /></div>{children}</>;
}

function Shell({ isAdmin, username, navigation, view, onLogout, children }: {
  isAdmin: boolean;
  username?: string;
  navigation: readonly NavigationEntry[];
  view?: string;
  onLogout: () => void;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <div className="deck-shell flex h-dvh bg-canvas">
      <Sidebar navigation={navigation} current={view} isAdmin={isAdmin} username={username} onNavigate={(path) => navigate(path)} onLogout={onLogout} />
      <main className="deck-main flex min-h-0 min-w-0 flex-1 flex-col overflow-auto">{children}</main>
    </div>
  );
}

/** A destination the reader's role may not visit goes back home: a member never sees the users screen. */
function RouteGuard({ isAdmin, navigation, children }: {
  isAdmin: boolean; navigation: readonly NavigationEntry[]; children: ReactNode;
}) {
  const { pathname } = useLocation();
  const known = destinationFor(pathname, navigation);
  return !known || canVisit(isAdmin ? "admin" : "usuario", pathname, navigation)
    ? children : <Navigate to="/" replace />;
}
