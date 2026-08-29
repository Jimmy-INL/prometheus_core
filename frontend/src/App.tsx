import { useEffect, useRef, useState } from "react";
import { ProjectView } from "@/layouts/ProjectView";
import { Login } from "@/components/Login";
import { api } from "@/lib/api/client";
import { chatStore } from "@/lib/store/chat";
import { chatProfileName, useChatType } from "@/lib/useChatType";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [chatType] = useChatType();
  const bootstrappedRef = useRef(false);

  // Auth probe — replaces the Chainlit `/user` fetch. 200 → authed, 401 → login.
  useEffect(() => {
    api
      .me()
      .then(() => setAuthed(true))
      .catch(() => setAuthed(false));
  }, []);

  // On auth, load config + create a session, then open the SSE stream. The profile
  // is chosen once at session start from the local chat-type toggle.
  useEffect(() => {
    if (authed && !bootstrappedRef.current) {
      bootstrappedRef.current = true;
      void chatStore.bootstrap(chatProfileName(chatType));
      chatStore.connect();
    }
  }, [authed, chatType]);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      /* clear client state regardless */
    }
    chatStore.disconnect();
    bootstrappedRef.current = false;
    setAuthed(false);
  };

  if (authed === null) return null;
  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;
  return <ProjectView onLogout={handleLogout} />;
}
