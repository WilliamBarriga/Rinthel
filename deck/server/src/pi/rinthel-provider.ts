import { streamSimple, createAssistantMessageEventStream } from "@earendil-works/pi-ai/compat";
import type { Api, Model, Provider } from "@earendil-works/pi-ai";
import type { Route } from "../model-routing/model-routing.js";
import type { ModelAccess } from "../session-proxy.js";

/**
 * pi's only provider: the Local model the route names, sent to the Session's proxy URL
 * (`session-proxy.ts`), which goes straight to llama-server. The key is a dummy; nobody reads it.
 *
 * There is no model to pick: `getModels()` is the route's one model. When the admin switches the
 * Local model, the proxy answers the next call `wrong_model` and moves the Session to the new route;
 * a turn that failed that way is retried once on the new model, switched to first with `setModel`
 * (the history is pi's, so it carries over).
 *
 * An ExtensionFactory: one instance per Session.
 */
export const RINTHEL_PROVIDER_ID = "rinthel";

const DUMMY_KEY = "dummy";

/** A Session with no Local model still needs a model; its calls get the proxy's 503 and its reason. */
const NO_MODEL = "sin-modelo";

/** What pi plans for an answer; never more than a quarter of the window, so the history keeps room. */
const MAX_OUTPUT_TOKENS = 32_000;
const FALLBACK_WINDOW = 32_768;

/** The model pi runs for a route: the route's own, with its window and reasoning format, sent to the Session's proxy. */
export function routedModel(sessionUrl: string, route: Route | null): Model<Api> {
  const id = route?.model ?? NO_MODEL;
  const contextWindow = route?.contextWindow ?? FALLBACK_WINDOW;
  return {
    id,
    name: id,
    api: "openai-completions",
    provider: RINTHEL_PROVIDER_ID,
    // OpenAI's SDK appends `/chat/completions`.
    baseUrl: `${sessionUrl}/v1`,
    // Every Local model of the catalog can think; the Session's effort says how much.
    reasoning: true,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow,
    maxTokens: Math.min(MAX_OUTPUT_TOKENS, Math.floor(contextWindow / 4)),
    compat: {
      supportsStore: false,
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      supportsUsageInStreaming: true,
      supportsStrictMode: false,
      maxTokensField: "max_tokens",
      // How llama-server's chat template is told the effort: the Local model says (catalog entry).
      thinkingFormat: route?.reasoningFormat ?? "qwen-chat-template",
    },
  } as Model<Api>;
}

const sameModel = (a: Model<Api>, b: Model<Api>) => a.id === b.id && a.contextWindow === b.contextWindow;
const sameRoute = (a: Route | null, b: Route | null) => JSON.stringify(a) === JSON.stringify(b);

export function rinthelProvider(access: ModelAccess, onModelChange: (model: Model<Api>) => Promise<void>): Provider<Api> {
  const model = () => routedModel(access.url, access.route());
  const provider: Provider<Api> = {
    id: RINTHEL_PROVIDER_ID,
    name: "Rinthel",
    auth: {
      apiKey: {
        name: "Local model",
        resolve: async () => ({ auth: { apiKey: DUMMY_KEY }, source: "session proxy" }),
      },
    },
    getModels: () => [model()],
    stream: (attempted, context, options) => provider.streamSimple!(attempted, context, options as any),
    streamSimple: (attempted, context, options) => {
      const out = createAssistantMessageEventStream();
      const routeBefore = access.route();
      void (async () => {
        // `start` is held back until the attempt answers or fails: a retried turn is one turn to pi.
        let held: unknown;
        for await (const event of streamSimple(attempted, context, options as any)) {
          if (event.type === "start") {
            held = event;
            continue;
          }
          // The proxy moved the Session to another Local model during this attempt: switch and go again.
          if (event.type === "error" && access.route() && !sameRoute(access.route(), routeBefore)) {
            const fresh = model();
            const ready = sameModel(fresh, attempted) || (await onModelChange(fresh).then(() => true, () => false));
            if (ready) {
              for await (const retried of streamSimple(fresh, context, options as any)) out.push(retried);
              return;
            }
          }
          if (held) {
            out.push(held as any);
            held = undefined;
          }
          out.push(event);
        }
      })();
      return out;
    },
  };
  return provider;
}

export function rinthelProviderExtension(...args: Parameters<typeof rinthelProvider>) {
  return (pi: any): void => {
    pi.registerProvider(rinthelProvider(...args));
  };
}
