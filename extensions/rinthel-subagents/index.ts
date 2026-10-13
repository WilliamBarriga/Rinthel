import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerSubagent } from "./tool.ts";

export default function (pi: ExtensionAPI) {
	registerSubagent(pi);
}
