import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * The app previously had no error boundary anywhere in the React tree, so
 * a rendering crash in any one page (a bad API response shape, a null
 * dereference, etc.) took down the entire app instead of just that page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error in app tree:", error, info.componentStack);
  }

  private handleReload = () => {
    this.setState({ error: null });
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
          <p className="text-card-title text-primary">Something went wrong</p>
          <p className="max-w-sm text-body text-muted-foreground">
            This page hit an unexpected error. Reloading usually fixes it —
            if it keeps happening, it's worth a closer look.
          </p>
          <Button variant="secondary" onClick={this.handleReload}>
            Reload
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
