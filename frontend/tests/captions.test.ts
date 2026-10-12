import assert from "node:assert/strict";
import {test} from "node:test";
import {isCaption} from "../src/api/captions.ts";
import {readFileSync} from "node:fs";
import ts from "typescript";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
test("temporary caption contract preserves role/timing and rejects unsafe or unbounded events",()=>{
  const value={kind:"caption",role:"candidate",sequence:1,start:0,end:2,text:"Synthetic Python answer"};
  assert.ok(isCaption(value));
  for(const patch of [{role:"admin"},{sequence:0},{end:121},{start:-1},{end:-1},{text:"unsafe\0text"},{text:"x".repeat(1001)},{token:"secret"}])
    assert.ok(!isCaption({...value,...patch}));
});

test("production caption panel starts without consent and never captures media during rendering",async()=>{
  // Compile the existing TSX in memory with the already installed compiler.
  let compiled=ts.transpileModule(readFileSync(new URL("../src/components/InterviewCaptions.tsx",import.meta.url),"utf8"),
    {compilerOptions:{module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  for(const name of ["react","react/jsx-runtime"]) compiled=compiled.replaceAll(`"${name}"`,JSON.stringify(import.meta.resolve(name)));
  compiled=compiled.replace('"../api/captions"',JSON.stringify(new URL("../src/api/captions.ts",import.meta.url).href));
  const {default:Panel}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
  for(const connected of [false,true]) {
    const html=renderToStaticMarkup(createElement(Panel,{connected,candidate:true,microphone:()=>{throw Error("Must not capture before both consents");}}));
    assert.ok(html.includes("Both participants must consent"));
    assert.ok(html.includes("No recording or saved transcript"));
    assert.ok(!html.includes('checked=""'));
    assert.match(html,/disabled=""[^>]*>Consent to captions/);
    assert.ok(html.includes('aria-label="Live captions"'));
  }
});
