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
    <div className="relative flex items-center justify-center h-screen bg-gray-950 overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_60%_50%,rgba(79,70,229,0.15),transparent_70%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_20%_80%,rgba(99,102,241,0.08),transparent_60%)]" />

      {/* Grid texture */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:64px_64px]" />
      <div>
      <div className="relative w-full max-w-lg px-6 space-y-8">
        {/* Logo */}
        <div className="grid justify-items-center -mt-6">
          <img src="/public/logo_dark.png" alt="Prometheus" />
          <span className="text-lg text-gray-500 -mt-6">AI orchestration for nuclear engineering</span>
        </div>
      </div>
      </div>
      <div className="relative w-full max-w-sm px-6 space-y-8">
        {/* Form */}
        <div className="space-y-3">
          {error && (
            <div className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-400 uppercase tracking-wider">Username</label>
            <input
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
              placeholder="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-400 uppercase tracking-wider">Password</label>
            <input
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
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

          <div className="divider divider-primary text-xs text-primary py-4">OR</div>

          <a 
            href="/login/oauth/authorize"
            className="w-full flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
          >
            Continue with Okta
          </a>
        </div>
      </div>
    </div>
  );
}
