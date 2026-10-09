import { useEffect, useState } from "react";
import type { ReactNode, FormEvent } from "react";
import { account, signIn, signOut } from "../api/session";
import type { RecruiterAccount } from "../api/session";

export default function RecruiterSignIn({children}: {children: ReactNode | ((user: RecruiterAccount) => ReactNode)}) {
  const [user, setUser] = useState<RecruiterAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void account().then(value => {if (alive) setUser(value);}).catch(() => {if (alive) setError("Sign-in service is unavailable. Check database readiness.");})
      .finally(() => {if (alive) setLoading(false);});
    const expired = () => {setUser(null); setPassword(""); setError("Your session expired. Sign in again.");};
    window.addEventListener("talenttrace-session-expired", expired);
    return () => {alive = false; window.removeEventListener("talenttrace-session-expired", expired);};
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (loading) return;
    setLoading(true); setError("");
    try {setUser(await signIn(email, password)); setPassword("");}
    catch (failure) {setError(failure instanceof Error ? failure.message : "Sign-in failed.");}
    finally {setLoading(false);}
  }
  if (user) return <div key={user.id}>
    <div className="account-bar"><span>Signed in as {user.email}</span><button className="button button-secondary" disabled={loading} onClick={() => {
      setLoading(true); setError("");
      void signOut().then(() => setUser(null)).catch(() => setError("Sign-out was not confirmed.")).finally(() => setLoading(false));
    }}>Sign out</button>{error && <p role="alert">{error}</p>}</div>{typeof children === "function" ? children(user) : children}
  </div>;
  return <main className="app-shell"><section className="card"><h1>Sign in to TalentTrace AI</h1>
    <p>Your jobs and conversations belong to your recruiter account.</p>
    <form onSubmit={submit}><div className="field"><label htmlFor="recruiter-email">Email</label><input id="recruiter-email" type="email" autoComplete="username" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} required /></div>
      <div className="field"><label htmlFor="recruiter-password">Password</label><input id="recruiter-password" type="password" autoComplete="current-password" maxLength={128} value={password} onChange={e => setPassword(e.target.value)} required /></div>
      {error && <p role="alert">{error}</p>}<button className="button button-primary" disabled={loading}>{loading ? "Checking session…" : "Sign in"}</button>
    </form><p className="helper-text">Ask your administrator for an account. There is no public registration.</p>
  </section></main>;
}
