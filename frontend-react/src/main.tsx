import React from "react";
import ReactDOM from "react-dom/client";
import { RecoilRoot } from "recoil";
import { ChainlitAPI, ChainlitContext } from "@chainlit/react-client";
import App from "./App";
import "./index.css";

const CHAINLIT_SERVER = "http://localhost:8500";

const apiClient = new ChainlitAPI(CHAINLIT_SERVER, "webapp");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ChainlitContext.Provider value={apiClient}>
      <RecoilRoot>
        <App />
      </RecoilRoot>
    </ChainlitContext.Provider>
  </React.StrictMode>
);
