import type { APIRequestContext, Page } from '@playwright/test';
import { DEMO_USER } from './scenario.mts';

export interface Credentials { username: string; password: string }

/** Opens `path` and signs in through the login form, as the demo admin unless other `credentials` are given. */
export async function login(page: Page, path = '/', credentials: Credentials = DEMO_USER) {
  await page.goto(path);
  await page.getByPlaceholder('Usuario').fill(credentials.username);
  await page.getByPlaceholder('Contraseña').fill(credentials.password);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
}

/** Creates a miembro as the demo admin through the users API and answers its id. */
export async function createMember(request: APIRequestContext, credentials: Credentials): Promise<number> {
  const admin = await request.post('/api/auth/login', { data: DEMO_USER });
  if (!admin.ok()) throw new Error(`demo login failed: ${admin.status()}`);
  const user = await request.post('/api/identity/users', { data: { ...credentials, role: 'miembro' } });
  if (!user.ok()) throw new Error(`member creation failed: ${user.status()}`);
  return (await user.json()).id;
}
