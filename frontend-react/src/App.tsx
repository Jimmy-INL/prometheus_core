import { useEffect, useRef, useState } from "react";
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

  const connectedRef = useRef(false);
  useEffect(() => {
    if (authed && !connectedRef.current) {
      connectedRef.current = true;
      connect({ userEnv: {}, transports: ["websocket"] });
    }
  }, [authed, connect]);

  useEffect(() => {
    const s = session?.socket;
    if (!s) return;
    const ts = () => new Date().toISOString().slice(11, 23);
    const onConnect = () => console.log(`[socket ${ts()}] connect id=${s.id}`);
    const onDisconnect = (reason: string) =>
      console.log(`[socket ${ts()}] disconnect reason=${reason} id=${s.id}`);
    const onReconnect = (n: number) =>
      console.log(`[socket ${ts()}] reconnect attempt=${n}`);
    s.on("connect", onConnect);
    s.on("disconnect", onDisconnect);
    s.io.on("reconnect_attempt", onReconnect);
    console.log(`[socket ${ts()}] listener attached, currently connected=${s.connected} id=${s.id}`);
    return () => {
      s.off("connect", onConnect);
      s.off("disconnect", onDisconnect);
      s.io.off("reconnect_attempt", onReconnect);
    };
  }, [session?.socket]);

  const handleLogout = async () => {
    const res = await fetch("/logout", {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return;
    disconnect();
    connectedRef.current = false;
    resetSessionId();
    resetThreadId();
    resetThreadIdToResume();
    setAuthed(false);
  };

  if (authed === null) return null;
  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;
  return <ProjectView onLogout={handleLogout} />;
}
