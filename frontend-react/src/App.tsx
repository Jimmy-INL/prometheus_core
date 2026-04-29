import { useEffect } from "react";
import { useRecoilValue } from "recoil";
import { sessionState, useChatSession, useChatData } from "@chainlit/react-client";

const userEnv = {};

export default function App() {
  const { connect } = useChatSession();
  const session = useRecoilValue(sessionState);
  const { connected } = useChatData();

  useEffect(() => {
    if (session?.socket.connected) return;

    fetch("/user", { credentials: "include" }).then((res) => {
      console.log("user status:", res.status);
      if (res.ok) connect({ userEnv });
    });
  }, [connect]);

  console.log("connected:", connected, "session:", session);

  return (
    <div style={{ color: "white", padding: 20 }}>
      Socket: {connected ? "✓ connected" : "connecting..."}
    </div>
  );
}
