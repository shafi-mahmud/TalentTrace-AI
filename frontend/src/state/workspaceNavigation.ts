import type {WorkspaceMode} from '../components/cvIntakePresentation';

// Candidate bearer-token routes are handled separately by App, before recruiter navigation.
export function workspaceModeFromHash(hash:string):WorkspaceMode {
  return hash==='#interview-scheduling' ? 'scheduling' : hash==='#candidate-screening' ? 'cv' : 'jd';
}
export function workspaceHash(mode:WorkspaceMode):string {
  return mode==='scheduling' ? 'interview-scheduling' : mode==='cv' ? 'candidate-screening' : 'jd-assistant';
}
