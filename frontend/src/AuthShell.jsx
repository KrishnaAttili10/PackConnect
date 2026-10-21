import { useEffect, useState } from "react";
import App from "./App";
import RegistrationForm from "./RegistrationForm";
import "./AuthShell.css";

const pages = {
  about: {
    title: "Good advice starts with a connection.",
    intro: "PackConnect helps NC State students learn from peers who have been there.",
    sections: [
      ["Built around your courses", "Find peers by completed courses, program, interests, skills, and the topics you want help with. Read their profiles and start a conversation."],
      ["Give back to your Pack", "Create a profile, share your experience, and choose whether you are available to advise. A useful tip can make someone else's semester easier."],
      ["A student-built prototype", "PackConnect is a course project, not an official NC State service. Sample profiles are fictional. Course histories are self-reported, and advice requests and accepted-request conversations are saved in the backend."],
    ],
  },
  privacy: {
    title: "Privacy policy",
    intro: "How this PackConnect prototype handles information. Updated October 20, 2026.",
    sections: [
      ["Information you provide", "Registration stores your email, a password hash, and your student profile. Profile information includes your name, program, year, bio, interests, courses, skills, and advice topics. Avoid entering sensitive information into this prototype."],
      ["What other people can see", "Student profiles are discoverable through the API and app. Email addresses and password hashes are not included in public profile responses. Advice requests are visible only to their sender and recipient. After acceptance, only those two participants can read or send messages in that conversation."],
      ["Storage and session cookies", "The current backend stores accounts, profiles, and messages in its SQLite database. A session cookie keeps you signed in for up to eight hours. Requests and chat messages persist across visits in the backend database. No analytics or advertising trackers are added by this app."],
      ["Prototype limitations and requests", "This version has no automated account-deletion or password-reset flow. Contact the project maintainers through the repository for data questions, without posting passwords or personal records. Access controls and retention procedures are still being developed."],
    ],
  },
  terms: {
    title: "Terms & conditions",
    intro: "Guidelines for using the PackConnect student prototype. Updated October 20, 2026.",
    sections: [
      ["Use the app respectfully", "Share accurate information, respect other students, and contact peers only for relevant academic advice. Do not harass, impersonate others, distribute private information, or misuse accounts."],
      ["Keep academic integrity in mind", "Share study strategies and experiences. Do not request or distribute restricted assignments, exam answers, or material that violates your course policies."],
      ["Peer advice has limits", "Profiles and course completion are self-reported. Advice reflects individual experiences and may be incomplete or outdated. Check official university sources for academic requirements and decisions."],
      ["An evolving course project", "Features and stored data may change during development. The app is not an official university service and does not guarantee availability, message delivery, or the accuracy of user content. Use fictional data when testing."],
    ],
  },
};

function currentRoute() {
  return window.location.hash.replace(/^#\/?/, "") || "login";
}

function Footer() {
  return <footer className="auth-footer"><span>Made for students. Built for connection.</span><nav aria-label="Information"><a href="#/about">About PackConnect</a><a href="#/privacy">Privacy policy</a><a href="#/terms">Terms &amp; conditions</a></nav></footer>;
}

export default function AuthShell() {
  const [route, setRoute] = useState(currentRoute);
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    function navigate() { setRoute(currentRoute()); setError(""); window.scrollTo(0, 0); }
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/auth/me", { signal: controller.signal })
      .then(async (response) => {
        if (response.ok) setUser((await response.json()).student);
      })
      .catch(() => {})
      .finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (checking) return;
    if ((route === "app" || route.startsWith("app/")) && !user) window.location.hash = "/login";
    if (user && (route === "login" || route === "register")) window.location.hash = "/app";
    document.title = `${pages[route]?.title || (route.startsWith("app/profile") ? "My profile" : route.startsWith("app/students/") ? "Student profile" : route.startsWith("app/chat/") ? "Conversation" : route === "app/requests" ? "Advice requests" : route === "app" ? "Find your people" : route === "register" ? "Create account" : "Sign in")} | PackConnect`;
  }, [route, user, checking]);

  async function signIn(event) {
    event.preventDefault();
    if (busy) return;
    const fields = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: fields.get("email"), password: fields.get("password") }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Unable to sign in.");
      setUser(data.student);
      window.location.hash = "/app";
    } catch (err) {
      setError(err instanceof SyntaxError || err instanceof TypeError ? "We couldn't reach PackConnect. Check that the backend is running and try again." : err.message);
    } finally { setBusy(false); }
  }

  async function signOut() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("Unable to sign out. Please try again.");
      setUser(null); window.location.hash = "/login";
      setNotice("You've been signed out.");
    } catch { setError("Couldn't sign out. Check your connection and try again."); }
    finally { setBusy(false); }
  }

  if (checking && !pages[route]) return <div className="auth-loading" role="status">Connecting to your Pack…</div>;
  if (user && (route === "app" || route.startsWith("app/"))) return <>{error && <div className="auth-global-error" role="alert">{error}</div>}<App user={user} onLogout={signOut} route={route} onUserUpdated={setUser} /></>;

  return <div className="auth-site">
    <header className="auth-header"><a className="auth-brand" href={user ? "#/app" : "#/login"}><span className="auth-brand-mark" aria-hidden="true">P<span>c</span></span>PackConnect<span className="auth-beta">STUDENT EDITION</span></a><a className="auth-about" href={user ? "#/app" : "#/about"}>{user ? "Back to the app" : "Meet PackConnect"}<span aria-hidden="true"> ↗</span></a></header>
    {pages[route] ? <main className="info-page"><a className="auth-back" href={user ? "#/app" : "#/login"}>← {user ? "Back to the app" : "Back to sign in"}</a><span className="auth-eyebrow">THE PACKCONNECT PROJECT</span><h1>{pages[route].title}</h1><p className="info-intro">{pages[route].intro}</p>{pages[route].sections.map(([title, text]) => <section key={title}><h2>{title}</h2><p>{text}</p></section>)}<a className="auth-primary info-cta" href={user ? "#/app" : "#/register"}>{user ? "Find your people" : "Join your Pack"} →</a></main> : <main className="auth-layout">
      <section className="auth-story"><span className="auth-eyebrow">YOUR NEXT CHAPTER STARTS WITH A CONNECTION</span><h1>Find your people.<br />Find your <em>way.</em></h1><p>Big questions. Shared experiences. Connect with students who have taken your courses—and take your next step with confidence.</p><div className="auth-course-art" aria-hidden="true"><div className="art-orbit" /><span className="art-course art-course-one">CSC 510 <b>↗</b></span><span className="art-course art-course-two">Your next connection <b>✦</b></span><div className="art-profile"><div className="art-avatar">AM</div><div><strong>A fresh perspective</strong><span>One conversation away</span></div><span className="art-check">✓</span></div></div><div className="auth-story-bottom"><span className="auth-story-rule" />A little guidance. A lot of possibility.</div></section>
      <section className={`auth-card ${route === "register" ? "auth-register-card" : ""}`} aria-label={route === "register" ? "Create account" : "Sign in"}>
        {route === "register" ? <><a className="auth-back" href="#/login">← Back to sign in</a><RegistrationForm apiUrl="" onClose={() => { window.location.hash = "/login"; }} onRegistered={() => { setNotice("Account created. Sign in to get started."); window.location.hash = "/login"; }} /><p className="auth-fine-print">Read our <a href="#/privacy">privacy policy</a> and <a href="#/terms">terms &amp; conditions</a> before creating an account.</p></> : <><span className="auth-card-kicker">WELCOME TO YOUR PACK</span><h2>Good to see you.</h2><p className="auth-card-subtitle">Sign in to find a little direction—and your people.</p>{notice && <p className="auth-success" role="status">{notice}</p>}<form onSubmit={signIn}><fieldset disabled={busy}><label htmlFor="login-email">Email address</label><input id="login-email" name="email" type="email" placeholder="you@example.edu" autoComplete="username" maxLength={254} required /><label htmlFor="login-password">Password</label><div className="auth-password"><input id="login-password" name="password" type={showPassword ? "text" : "password"} placeholder="Enter your password" autoComplete="current-password" maxLength={128} required /><button type="button" onClick={() => setShowPassword(!showPassword)} aria-controls="login-password" aria-pressed={showPassword} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button></div>{error && <p className="auth-error" role="alert">{error}</p>}<button className="auth-primary" type="submit">{busy ? "Signing in…" : "Sign in"}<span aria-hidden="true">→</span></button></fieldset></form><div className="auth-divider"><span>New around here?</span></div><a className="auth-secondary" href="#/register">Create an account <span aria-hidden="true">↗</span></a><p className="auth-fine-print">Your next connection is closer than you think.<br />Explore our <a href="#/privacy">privacy policy</a> and <a href="#/terms">terms &amp; conditions</a>.</p></>}
      </section>
    </main>}
    <Footer />
  </div>;
}
