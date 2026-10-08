import { useState } from "react";
import RecruiterChat from "./components/RecruiterChat";
import { RecruiterChatPage } from "./components/chatPresentation";
import CvIntake from "./components/CvIntake";
import { WorkspaceNavigation } from "./components/cvIntakePresentation";
import type { WorkspaceMode } from "./components/cvIntakePresentation";
import type { ScreeningSuggestions } from "./types/screening";

export default function App() {
  const [mode, setMode] = useState<WorkspaceMode>("jd");
  const [suggestions, setSuggestions] = useState<ScreeningSuggestions | null>(null);
  return <>
    <WorkspaceNavigation mode={mode} onChange={setMode} />
    <div hidden={mode !== "jd"}><RecruiterChatPage><RecruiterChat onReviewCriteria={value => {setSuggestions(value); setMode("cv");}} /></RecruiterChatPage></div>
    <div hidden={mode !== "cv"}><CvIntake suggestions={suggestions} /></div>
  </>;
}
