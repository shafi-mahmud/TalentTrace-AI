export interface CvAISelection {provider:string;externalConfirmed:boolean;}
export function cvProviderReady(selection?:CvAISelection):boolean {
 return !!selection && ['groq','ollama:qwen2.5:1.5b','ollama:smollm2:360m-instruct-q4_K_M'].includes(selection.provider)
  && (selection.provider!=='groq'||selection.externalConfirmed===true);
}
export function cvProviderHeaders(selection?:CvAISelection):Record<string,string> {
 if(!cvProviderReady(selection))throw Error('Select CV AI and confirm external processing when applicable.');
 return {'X-TalentTrace-AI-Provider':selection!.provider,...(selection!.provider==='groq'?{'X-TalentTrace-External-Processing':'confirmed'}:{})};
}
