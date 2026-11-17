/** The landing screen after login: who is in. The chat replaces it with the Sessions and the composer. */
export function HomePage({ username, isAdmin }: { username?: string; isAdmin: boolean }) {
  return (
    <div className="px-5 pt-5">
      <p className="ui-eyebrow">Inicio</p>
      <h1 className="ui-title">{username ? `Hola, ${username}` : "Hola"}</h1>
      <p className="ui-description">{isAdmin ? "Entraste como administrador." : "Entraste como miembro."}</p>
    </div>
  );
}
