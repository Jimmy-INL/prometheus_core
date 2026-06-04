import ReactDOM from "react-dom/client";
import { RecoilRoot } from "recoil";
import { ChainlitAPI, ChainlitContext } from "@chainlit/react-client";
import App from "./App";
import "./index.css";

const apiClient = new ChainlitAPI(window.location.origin, "webapp");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <ChainlitContext.Provider value={apiClient}>
    <RecoilRoot>
      <App />
    </RecoilRoot>
  </ChainlitContext.Provider>
);
