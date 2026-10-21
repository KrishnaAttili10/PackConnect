import { useEffect, useRef, useState } from "react";
import { api, json } from "./messagingApi";
import "./Messaging.css";

export function ConnectionRequestForm({ student, defaultCourse, onRequestCreated }) {
  const [form, setForm] = useState({ course_code: defaultCourse, advice_topic: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      await api("/api/requests", json("POST", { ...form, recipient_id: student.id }));
      setSuccess(true); onRequestCreated();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  if (success) return <section className="request-form"><p className="message-success" role="status">Request sent to {student.name}. Chat will unlock if they accept.</p><a href="#/app/requests">View your requests</a></section>;
  return <form className="request-form" onSubmit={submit}><h3>Request advice from {student.name}</h3><p className="profile-note">Your signed-in profile identifies you. Send some context first; private chat unlocks after acceptance.</p><fieldset className="request-fields" disabled={busy}>
    <label>Course<input value={form.course_code} onChange={(e) => setForm({ ...form, course_code: e.target.value })} maxLength={30} required placeholder="CSC 510" /></label>
    <label>Advice topic<input value={form.advice_topic} onChange={(e) => setForm({ ...form, advice_topic: e.target.value })} maxLength={80} required placeholder="Projects, workload, preparation" /></label>
    <label>Your request<textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} maxLength={1000} rows={4} required placeholder="What would you like to learn from their experience?" /></label>
    {error && <p className="error-message" role="alert">{error}</p>}<button type="submit" disabled={!form.course_code.trim() || !form.advice_topic.trim() || !form.message.trim()}>{busy ? "Sending..." : "Send request"}</button>
  </fieldset></form>;
}

export function RequestInbox({ user, requests, loading, error, onRefresh }) {
  const [tab, setTab] = useState("incoming");
  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState("");
  async function respond(id, status) {
    if (busy !== null) return;
    setBusy(id); setActionError("");
    try { await api(`/api/requests/${id}`, json("PATCH", { status })); await onRefresh(); }
    catch (err) { setActionError(err.message); }
    finally { setBusy(null); }
  }
  const visible = requests.filter((item) => tab === "incoming" ? item.recipient_id === user.id : item.sender_id === user.id);
  return <section className="request-panel"><div className="section-heading"><div><h2>Your requests</h2><p>Accept a request to start a private conversation. Requests and messages are saved across visits.</p></div><button type="button" onClick={onRefresh}>Refresh</button></div>
    <div className="request-tabs" aria-label="Request direction"><button type="button" aria-pressed={tab === "incoming"} onClick={() => setTab("incoming")}>Incoming</button><button type="button" aria-pressed={tab === "outgoing"} onClick={() => setTab("outgoing")}>Outgoing</button></div>
    {(error || actionError) && <p className="error-message" role="alert">{actionError || error}</p>}
    {loading ? <p role="status">Loading requests...</p> : visible.length === 0 ? <p className="empty-state">No {tab} requests yet. <a href="#/app">Find peers</a></p> : <div className="request-list">{visible.map((item) => {
      const incoming = item.recipient_id === user.id;
      const peerId = incoming ? item.sender_id : item.recipient_id;
      const peerName = incoming ? item.sender_name : item.recipient_name;
      return <article className="request-card" key={item.id}><div><div className="request-card-header"><a href={`#/app/students/${peerId}`}>{peerName}</a><span className={`status-badge ${item.status}`}>{item.status}</span></div><p><strong>{item.course_code}</strong> · {item.advice_topic}</p><p className="preserve-lines">{item.message}</p><time dateTime={item.created_at.replace(" ", "T") + "Z"}>{new Date(item.created_at.replace(" ", "T") + "Z").toLocaleString()}</time></div><div className="request-actions">
        {item.status === "pending" && incoming && <><button type="button" disabled={busy !== null} onClick={() => respond(item.id, "accepted")}>{busy === item.id ? "Saving..." : "Accept"}</button><button type="button" disabled={busy !== null} onClick={() => respond(item.id, "declined")}>Decline</button></>}
        {item.status === "pending" && !incoming && <span className="profile-note">Waiting for a response</span>}
        {item.status === "accepted" && <a className="chat-open" href={`#/app/chat/${item.id}`}>Open chat</a>}
        {item.status === "declined" && <span className="profile-note">Chat is unavailable</span>}
      </div></article>;
    })}</div>}
  </section>;
}

export function Conversation({ requestId, user }) {
  const [record, setRecord] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sendError, setSendError] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const log = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    let cursor = 0;
    let timer;
    async function poll() {
      try {
        const data = await api(`/api/requests/${requestId}/messages?after_id=${cursor}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRecord(data.request); setError("");
        if (data.messages.length) {
          cursor = data.messages[data.messages.length - 1].id;
          setMessages((previous) => [...new Map([...previous, ...data.messages].map((m) => [m.id, m])).values()].sort((a, b) => a.id - b.id));
        }
        setLoading(false);
        timer = setTimeout(poll, data.has_more ? 0 : 3000);
      } catch (err) {
        if (!controller.signal.aborted) { setError(err.message); setLoading(false); timer = setTimeout(poll, 5000); }
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [requestId]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [messages.length]);
  async function send(event) {
    event.preventDefault();
    if (sending || !body.trim()) return;
    setSending(true); setSendError("");
    try {
      const data = await api(`/api/requests/${requestId}/messages`, json("POST", { body }));
      setMessages((previous) => [...new Map([...previous, data.message].map((m) => [m.id, m])).values()].sort((a, b) => a.id - b.id));
      setBody("");
    } catch (err) { setSendError(err.message); }
    finally { setSending(false); }
  }
  const peerName = record && (record.sender_id === user.id ? record.recipient_name : record.sender_name);
  return <section className="conversation"><a className="profile-back" href="#/app/requests">Back to requests</a><header className="conversation-heading"><h2>{peerName ? `Chat with ${peerName}` : "Conversation"}</h2>{record && <p>{record.course_code} · {record.advice_topic} <span className="status-badge accepted">Connected</span></p>}</header>
    {error && <p className="error-message" role="alert">{error}</p>}{loading && <p role="status">Loading conversation...</p>}
    {record && <><p className="conversation-context"><strong>Original request:</strong> {record.message}</p><div className="chat-log" role="log" aria-label="Conversation messages" aria-live="polite" ref={log}>{messages.length === 0 ? <p className="empty-state">You're connected. Say hello!</p> : messages.map((item) => <article className={item.sender_id === user.id ? "chat-bubble own" : "chat-bubble"} key={item.id}><strong>{item.sender_id === user.id ? "You" : peerName}</strong><p>{item.body}</p><time dateTime={item.created_at.replace(" ", "T") + "Z"}>{new Date(item.created_at.replace(" ", "T") + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></article>)}</div><form className="chat-compose" onSubmit={send}><label htmlFor="chat-message">Message to {peerName}</label><textarea id="chat-message" value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={3} placeholder="Write a message..." disabled={sending} required /><div><span>{body.length}/2000 · Updates automatically</span><button type="submit" disabled={sending || !body.trim()}>{sending ? "Sending..." : "Send message"}</button></div>{sendError && <p className="error-message" role="alert">{sendError}</p>}</form></>}
  </section>;
}
