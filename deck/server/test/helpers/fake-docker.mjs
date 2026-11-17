/** A Docker Engine API double (`DockerApi`): just the endpoints the browser runtime calls, state in maps. */
export class FakeDocker {
  containers = new Map();
  volumes = new Set();
  pulls = [];

  constructor(opts = {}) {
    this.opts = { available: true, image: true, ...opts };
  }

  available() {
    return this.opts.available;
  }

  async imagePresent() {
    return this.opts.image;
  }

  async pullImage(image, onProgress) {
    this.pulls.push(image);
    onProgress("Downloading 50%");
    this.opts.image = true;
  }

  async request(method, path, body) {
    const url = new URL(path, "http://docker");
    const p = url.pathname;
    if (method === "POST" && p === "/volumes/create") {
      this.volumes.add(body.Name);
      return { status: 201, body: {} };
    }
    if (method === "POST" && p === "/containers/create") {
      const name = url.searchParams.get("name");
      if (this.containers.has(name)) return { status: 409, body: { message: "Conflict" } };
      this.containers.set(name, { running: false, spec: body });
      return { status: 201, body: { Id: name } };
    }
    const v = p.match(/^\/volumes\/([^/]+)$/);
    if (v && method === "DELETE") {
      return this.volumes.delete(v[1]) ? { status: 204, body: null } : { status: 404, body: { message: "No such volume" } };
    }
    const m = p.match(/^\/containers\/([^/]+)(?:\/(start|stop|json))?$/);
    if (m) {
      const c = this.containers.get(m[1]);
      if (!c) return { status: 404, body: { message: "No such container" } };
      if (method === "GET" && m[2] === "json") return { status: 200, body: { Id: m[1], State: { Running: c.running } } };
      if (method === "POST" && m[2] === "start") {
        if (c.running) return { status: 304, body: null };
        c.running = true;
        return { status: 204, body: null };
      }
      if (method === "POST" && m[2] === "stop") {
        if (!c.running) return { status: 304, body: null };
        c.running = false;
        return { status: 204, body: null };
      }
      if (method === "DELETE") {
        this.containers.delete(m[1]);
        return { status: 204, body: null };
      }
    }
    return { status: 400, body: { message: `unhandled ${method} ${path}` } };
  }
}
