/**
 * Resolves when pi accepts the prompt (its preflight passed), while a failure after that still goes
 * to `failedAfterAcceptance`: `session.prompt()` resolves only when the whole run ends.
 */
export function acceptPrompt(
  run: (preflight: (success: boolean) => void) => Promise<void>,
  failedAfterAcceptance: (error: unknown) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let accepted = false;
    try {
      void run((success) => { if (success) { accepted = true; resolve(); } }).then(resolve, (error) => {
        if (accepted) failedAfterAcceptance(error);
        else reject(error);
      });
    } catch (error) { reject(error); }
  });
}
