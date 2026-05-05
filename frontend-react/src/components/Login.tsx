import { useState } from "react";

interface Props {
  onSuccess: () => void;
}

export function Login({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    const res = await fetch("/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });
    setLoading(false);
    if (res.ok) {
      onSuccess();
    } else {
      setError("Invalid credentials");
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
          <button
            className="btn btn-primary w-full"
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>

          <div className="divider divider-neutral text-xs py-4">OR</div>

          <a
            href="/login/oauth/authorize"
            className="w-full flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-base-content text-sm font-medium py-2.5 rounded-lg transition-colors"
          >
            Continue with Okta
          </a>
        </div>
      </div>
    </div>
  );
}
