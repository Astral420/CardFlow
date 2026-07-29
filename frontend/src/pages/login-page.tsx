import { useState, type FormEvent } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage } from "@/lib/api";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(name, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm animate-lift-in rounded-2xl border border-border bg-surface p-8 shadow-float-lg">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img
            src="/favicon.png"
            alt="CardFlow"
            className="h-12 w-12 rounded-xl object-contain"
          />
          <div>
            <h1 className="text-section text-primary">CardFlow</h1>
            <p className="mt-1 text-caption text-muted-foreground">
              Sign in to continue processing batches
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="space-y-1.5">
            <label className="text-caption font-medium text-muted-foreground" htmlFor="name">
              Name
            </label>
            <Input
              id="name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your display name"
              autoComplete="username"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-caption font-medium text-muted-foreground" htmlFor="password">
              Password
            </label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password or the shared app passcode"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p className="rounded-xl bg-accent-rose px-3 py-2 text-caption text-accent-rose-foreground">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" disabled={isSubmitting} className="mt-1">
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="mt-6 border-t border-border pt-4 text-center">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-caption font-medium text-muted-foreground transition-colors hover:text-primary"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Dashboard (Guest mode)
          </Link>
        </div>
      </div>
    </div>
  );
}
