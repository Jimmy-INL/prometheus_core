import { useEffect } from "react";
import { useRecoilValue } from "recoil";
import { sessionState, useChatSession } from "@chainlit/react-client";
import { Chat } from "./components/Chat";
import { Login } from "./components/Login";

const userEnv = {};

export default function App() {
  const { connect } = useChatSession();
  const session = useRecoilValue(sessionState);

  useEffect(() => {
    if (session?.socket.connected) return;
    fetch("/user", { credentials: "include" }).then((res) => {
      if (res.ok) connect({ userEnv });
    });
  }, [connect]);

  // return <Chat />;
  return <Login onSuccess={() => console.log("logged in")} />;
}
