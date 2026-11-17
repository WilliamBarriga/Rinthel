# Policy de acceso declarada por ruta y revalidada contra la identidad

Al daemon lo llaman la TUI, Deck y usuarios con Panel token, cada uno con credenciales distintas. Cada ruta **declara su Access policy una sola vez**, como dependency de FastAPI (`rinthel/rinthel_tui/api/access.py`). La security de OpenAPI se deriva de esa misma declaración, y `rinthel/tests/daemon/test_route_policies.py` falla si una ruta declara cero policies o más de una, si una ruta protegida deja pasar a alguien sin credenciales, o si OpenAPI documenta otra cosa.

## Policies

Solo dicen *quién* llama:

- **`public`:** anónimo. Solo `POST /identity/login`, `/identity/refresh` y `/identity/logout`, que es como se consigue un Panel token; y `/docs`, `/redoc` y `/openapi.json` cuando `RINTHEL_DAEMON_DOCS=1`.
- **`service`:** la TUI o Deck, con `X-Rinthel-Service-Secret` comparado en tiempo constante. Con el secreto configurado vacío no pasa nadie. En `/ws/monitor` el secreto viaja en `?token=` y el rechazo es un close 4401 antes de `accept()`.
- **`service_as_user`:** Deck con el secreto de servicio actuando por un usuario que nombra en `X-Rinthel-User-Id`, nunca en el body. Cubre una sola ruta, `GET /identity/me/session-principal` (id y rol vigentes, para autorizar Sesiones y las rutas de administración de Deck); un usuario deshabilitado o borrado es 401.
- **`user`:** un Usuario con Panel token (`Authorization: Bearer`).
- **`admin`:** `user` con rol `admin`.

`any_of(...)` combina policies como alternativas y cuenta como una sola: `service_or_admin = any_of(service, admin)` protege `/theme` y `/openapi.json`.

## Revalidación

Las policies de usuario devuelven un `UserRow` leído de nuevo de `rinthel.db`, nunca los claims del token: del token solo se usa `sub`. Un admin degradado o deshabilitado pierde el acceso en su siguiente request, sin esperar a que expire el token. El costo es una lectura de SQLite por request.

## Roles

Solo `admin` y `miembro`, sin Grupos ni permisos por usuario. Solo el admin edita usuarios, incluida su propia contraseña; el miembro no tiene autoservicio. La propiedad de un recurso (dueño o admin) no es una policy: la decide el módulo dueño del recurso, que es quien lo carga.

## Consecuencias

- Una ruta nueva elige una policy existente; una policy nueva entra acá y en `access.py`.
- Los bodies inválidos son 422, el default de FastAPI, porque los modelos Pydantic son los tipos reales de request y response.
- `create_app(cfg)` guarda `cfg` en `app.state`: no hay un `cfg` global que las dependencies tengan que overridear.

## Opciones descartadas

- **Dueño o admin como policy:** necesita cargar el recurso, así que no se decide mirando el request.
- **Confiar en los claims del token:** un admin deshabilitado seguiría entrando hasta que expire el token (un día).
