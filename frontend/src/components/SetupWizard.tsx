import { useState } from "react";
import { api, ApiError } from "@/lib/api/client";

interface Props {
  onSuccess: () => void;
}

/**
 * First-run screen: shown instead of <Login> whenever GET /api/setup/status
 * reports `needs_setup: true` (no admin-plane `users` row exists yet). Creates
 * the first account -- always role "admin" server-side -- and logs it in
 * immediately, same as a successful <Login>.
 */
export function SetupWizard({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!username.trim() || !password) {
      setError("Username and password are required");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.bootstrap(username, password);
      onSuccess();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Another browser/tab won the race to bootstrap first. Reloading picks
        // up needs_setup: false and shows <Login> instead.
        setError("Setup was already completed. Reloading...");
        setTimeout(() => window.location.reload(), 1500);
      } else {
        setError("Could not create the admin account. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex items-center justify-center h-screen bg-base-100 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_60%_50%,rgba(79,70,229,0.15),transparent_70%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_20%_80%,rgba(99,102,241,0.08),transparent_60%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-size-[64px_64px]" />

      <div>
        <div className="relative w-full max-w-lg px-6 space-y-8">
          <div className="grid justify-items-center -mt-6">
            <img src="/logo_dark.png" alt="Prometheus" />
            <span className="text-lg text-base-content/50 -mt-6">AI orchestration for nuclear engineering</span>
          </div>
        </div>
      </div>

      <div className="relative w-full max-w-sm px-6 space-y-8">
        <div className="space-y-3">
          <div className="space-y-1">
            <h1 className="text-base font-medium">Welcome — set up your admin account</h1>
            <p className="text-xs text-base-content/50">
              This platform has no users yet. Create the first account below; it will be an administrator.
            </p>
          </div>
          {error && (
            <div role="alert" className="alert alert-error text-xs">
              {error}
            </div>
          )}
          <div className="space-y-2">
            <label className="label">
              <span className="label-text text-xs uppercase tracking-wider">Username</span>
            </label>
            <input
              className="input input-bordered w-full"
              placeholder="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <label className="label">
              <span className="label-text text-xs uppercase tracking-wider">Password</span>
            </label>
            <input
              className="input input-bordered w-full"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>
          <div className="space-y-2">
            <label className="label">
              <span className="label-text text-xs uppercase tracking-wider">Confirm password</span>
            </label>
            <input
              className="input input-bordered w-full"
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>
          <button className="btn btn-primary w-full" onClick={handleSubmit} disabled={loading}>
            {loading ? "Creating account..." : "Create admin account"}
          </button>
        </div>
      </div>
    </div>
  );
}
