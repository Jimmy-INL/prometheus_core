import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { AuthProvider } from "@/lib/api/types";
import { setCurrentUser } from "@/lib/store/session";
import { AuthError, AuthField, AuthLayout } from "./AuthLayout";

interface Props {
  onSuccess: () => void;
}

export function Login({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [providers, setProviders] = useState<AuthProvider[]>([]);

  // Best-effort: an empty list just means no "sign in with ..." buttons show,
  // never a hard error blocking the password form.
  useEffect(() => {
    api
      .listAuthProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

  const handleSubmit = async () => {
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      const user = await api.login(username, password);
      setCurrentUser(user);
      onSuccess();
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Enter your INL credentials to continue"
      onSubmit={handleSubmit}
    >
      <AuthError message={error} />

      <AuthField
        label="Username"
        placeholder="username"
        autoComplete="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoFocus
      />
      <AuthField
        label="Password"
        type="password"
        placeholder="••••••••"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />

      <button type="submit" className="btn btn-primary w-full" disabled={loading}>
        {loading ? "Signing in..." : "Sign in"}
      </button>

      {providers.length > 0 && (
        <>
          <div className="divider text-xs text-base-content/40">or</div>
          <div className="space-y-2">
            {providers.map((provider) => (
              <a
                key={provider.provider_id}
                className="btn btn-outline w-full"
                href={api.loginUrl(provider.provider_id)}
              >
                Sign in with {provider.display_name}
              </a>
            ))}
          </div>
        </>
      )}
    </AuthLayout>
  );
}