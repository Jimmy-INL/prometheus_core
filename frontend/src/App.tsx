import { useEffect, useRef, useState } from "react";
import { ProjectView } from "@/layouts/ProjectView";
import { Login } from "@/components/Login";
import { SetupWizard } from "@/components/SetupWizard";
import { api } from "@/lib/api/client";
import { chatStore } from "@/lib/store/chat";
import { chatProfileName, useChatType } from "@/lib/useChatType";

/**
 * Boot sequence, in order: "loading" while the two probes below settle,
 * "needs_setup" if no admin-plane user exists yet (first-run wizard takes
 * over), else "unauthed"/"authed" from the existing session-cookie probe.
 *
 * No router yet -- this is one more branch alongside the existing
 * Login/ProjectView split, not a new architecture. A router is worth
 * introducing once nested Admin pages (users, signing keys, OIDC providers)
 * land and actually need one.
 */
type BootState = "loading" | "needs_setup" | "unauthed" | "authed";

export default function App() {
  const [boot, setBoot] = useState<BootState>("loading");
  const [chatType] = useChatType();
  const bootstrappedRef = useRef(false);

  // Setup-status probe runs first: while no admin exists, /api/auth/me would
  // just 401 regardless, so there's nothing to gain by racing the two. If the
  // setup-status probe itself fails (e.g. admin-db unreachable), fall through
  // to the normal auth probe rather than getting stuck on "loading" forever.
  useEffect(() => {
    api
      .setupStatus()
      .then((status) => {
        if (status.needs_setup) {
          setBoot("needs_setup");
          return;
        }
        return api
          .me()
          .then(() => setBoot("authed"))
          .catch(() => setBoot("unauthed"));
      })
      .catch(() => {
        api
          .me()
          .then(() => setBoot("authed"))
          .catch(() => setBoot("unauthed"));
      });
  }, []);

  // On auth, load config + create a session, then open the SSE stream. The profile
  // is chosen once at session start from the local chat-type toggle.
  useEffect(() => {
    if (boot === "authed" && !bootstrappedRef.current) {
      bootstrappedRef.current = true;
      void chatStore.bootstrap(chatProfileName(chatType));
      chatStore.connect();
    }
  }, [boot, chatType]);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      /* clear client state regardless */
    }
    chatStore.disconnect();
    bootstrappedRef.current = false;
    setBoot("unauthed");
  };

  if (boot === "loading") return null;
  if (boot === "needs_setup") return <SetupWizard onSuccess={() => setBoot("authed")} />;
  if (boot === "unauthed") return <Login onSuccess={() => setBoot("authed")} />;
  return <ProjectView onLogout={handleLogout} />;
}
