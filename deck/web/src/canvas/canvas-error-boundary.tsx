import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Keeps a view that throws inside its own Canvas: the notice replaces only that Canvas and the
 * page around it carries on. It clears when `resetKey` changes (a new revision may be fine).
 * `onError` receives what was caught, for whoever logs it.
 */
export class CanvasErrorBoundary extends Component<{ resetKey: string; onError?: (error: Error, componentStack: string) => void; children: ReactNode }, { error: Error | null; key: string }> {
  state = { error: null as Error | null, key: this.props.resetKey };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  static getDerivedStateFromProps(props: { resetKey: string }, state: { error: Error | null; key: string }) {
    return props.resetKey === state.key ? null : { error: null, key: props.resetKey };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    // Reported where the app says (its logger, a test's recorder); never to `console` behind its back.
    this.props.onError?.(error, info.componentStack ?? "");
  }
  render() {
    if (this.state.error) return <p role="alert" className="canvas-error">This interface canvas could not be shown: {this.state.error.message}</p>;
    return this.props.children;
  }
}

