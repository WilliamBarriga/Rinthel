/** In-memory `BrowserDriver`: serves a fixed catalogue and records every call. */
export class FakeBrowserDriver {
  calls = [];
  released = [];
  constructor(tools, answer = () => ({ content: [{ type: "text", text: "ok" }], isError: false })) {
    this.tools = tools;
    this.answer = answer;
  }
  async catalogue() {
    return this.tools;
  }
  async call(endpoint, tool, args) {
    this.calls.push({ endpoint, tool, args });
    return this.answer(endpoint, tool, args);
  }
  async release(endpoint) {
    this.released.push(endpoint);
  }
}
