import { useState } from "react";
import RecruiterChat from "./components/RecruiterChat";
import { RecruiterChatPage } from "./components/chatPresentation";
import CvIntake from "./components/CvIntake";
import { WorkspaceNavigation } from "./components/cvIntakePresentation";
import type { WorkspaceMode } from "./components/cvIntakePresentation";

export default function App() {
  const [mode, setMode] = useState<WorkspaceMode>("jd");
  return <>
    <WorkspaceNavigation mode={mode} onChange={setMode} />
    <div hidden={mode !== "jd"}><RecruiterChatPage><RecruiterChat /></RecruiterChatPage></div>
    <div hidden={mode !== "cv"}><CvIntake /></div>
  </>;
}
