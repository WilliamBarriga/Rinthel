import type { ReactElement, ReactNode } from "react";
import { render, renderHook } from "@testing-library/react";
import { PortsProvider, type Ports } from "./context";
import { IsAdminContext } from "../auth/use-is-admin";
import { fakeAuthApi } from "./fakes/auth";
import { fakeUsersAdminApi } from "./fakes/users-admin";

/** Fakes for every port; a test overrides only the ones it cares about. */
export function fakePorts(overrides: Partial<Ports> = {}): Ports {
  return { authApi: fakeAuthApi(), usersAdminApi: fakeUsersAdminApi(), ...overrides };
}

/** `isAdmin` is the reader's role as `App` provides it; a test is an admin unless it says otherwise. */
function wrapperFor(ports: Ports, isAdmin = true) {
  return ({ children }: { children: ReactNode }) => <IsAdminContext.Provider value={isAdmin}><PortsProvider ports={ports}>{children}</PortsProvider></IsAdminContext.Provider>;
}

export function renderWithPorts(ui: ReactElement, ports: Ports = fakePorts(), options: { isAdmin?: boolean } = {}) {
  return render(ui, { wrapper: wrapperFor(ports, options.isAdmin) });
}

export function renderHookWithPorts<T, P = undefined>(hook: (props: P) => T, ports: Ports = fakePorts(), options: { initialProps?: P; isAdmin?: boolean } = {}) {
  const { isAdmin, ...rest } = options;
  return renderHook(hook, { wrapper: wrapperFor(ports, isAdmin), ...rest });
}
