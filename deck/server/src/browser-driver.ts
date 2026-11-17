/** One tool the browser offers, as MCP describes it: the schema is JSON Schema, passed through as is. */
export interface BrowserToolSpec {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

export interface BrowserToolResult {
  content: unknown[];
  isError: boolean;
}

/**
 * What the Agent's browser tools need from whatever drives a browser over CDP. The tools themselves
 * are the driver's (Playwright's), so the catalogue is asked for rather than copied here. A call
 * names the CDP endpoint it acts on: the Instance browser's, the same for every Session.
 */
export interface BrowserDriver {
  /** The tools offered, the same for every endpoint. */
  catalogue(): Promise<BrowserToolSpec[]>;
  call(endpoint: string, tool: string, args: Record<string, unknown>): Promise<BrowserToolResult>;
  /** Drops whatever is held open for this endpoint (its browser has stopped). Not an error if nothing is. */
  release(endpoint: string): Promise<void>;
}
