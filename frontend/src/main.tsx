import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { takeInvitation } from "./api/livekitInterview";
import "./index.css";


// Capture once outside StrictMode's repeated initialization, never in storage.
const invitation=window.location.pathname==="/interview-join"?takeInvitation(window.location,window.history):null;
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App initialInvitation={invitation} />
  </StrictMode>,
);
