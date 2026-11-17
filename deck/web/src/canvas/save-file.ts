import type { SavedFile } from "./use-session-canvases";

/** The browser's way to hand a text file to the person: a download through a temporary link. */
export function saveTextFile({ filename, text, mime }: SavedFile): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
