import { useEffect, useState } from "react";
import { useRecoilValue, useResetRecoilState } from "recoil";
import {
  sessionState,
  sessionIdState,
  currentThreadIdState,
  threadIdToResumeState,
  useChatSession,
} from "@chainlit/react-client";
import { ProjectView } from "@/layouts/ProjectView";
import { Login } from "@/components/Login";

export default function App() {
  const { connect, disconnect } = useChatSession();
  const session = useRecoilValue(sessionState);
  const resetSessionId = useResetRecoilState(sessionIdState);
  const resetThreadId = useResetRecoilState(currentThreadIdState);
  const resetThreadIdToResume = useResetRecoilState(threadIdToResumeState);
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/user", { credentials: "include" })
      .then((res) => setAuthed(res.ok));
  }, []);

  useEffect(() => {
    if (authed && !session?.socket.connected) {
      connect({ userEnv: {}, transports: ["websocket"] });
    }
  }, [authed, connect, session?.socket.connected]);

  const handleLogout = async () => {
    const res = await fetch("/logout", {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return;
    disconnect();
    resetSessionId();
    resetThreadId();
    resetThreadIdToResume();
    setAuthed(false);
  };

  if (authed === null) return null;
  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;
  return <ProjectView onLogout={handleLogout} />;
}
