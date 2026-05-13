import { useEffect, useState } from "react";
import { useRecoilValue } from "recoil";
import { sessionState, useChatSession } from "@chainlit/react-client";
import { ProjectView } from "@/layouts/ProjectView";
import { Login } from "@/components/Login";

export default function App() {
  const { connect } = useChatSession();
  const session = useRecoilValue(sessionState);
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/user", { credentials: "include" })
      .then((res) => setAuthed(res.ok));
  }, []);

  useEffect(() => {
    if (authed && !session?.socket.connected) {
      connect({ userEnv: {} });
    }
  }, [authed, connect, session?.socket.connected]);

  const handleLogout = async () => {
    await fetch("/logout", { credentials: "include" });
    setAuthed(false);
  };

  if (authed === null) return null;
  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;
  return <ProjectView onLogout={handleLogout} />;
}
