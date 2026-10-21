import { useEffect, useRef, useState } from "react";
import { api, json } from "./messagingApi";
import "./NotificationBell.css";

function describe(item) {
  if (item.kind === "request_received") return `${item.actor_name} wants to connect about ${item.course_code}.`;
  if (item.kind === "accepted") return `${item.actor_name} accepted your request. You can now chat.`;
  if (item.kind === "declined") return `${item.actor_name} declined your request about ${item.course_code}.`;
  return `${item.actor_name} sent you a message.`;
}

export default function NotificationBell({ route }) {
  const [open, setOpen] = useState(false);
  const [feed, setFeed] = useState({ notifications: [], unread_count: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const root = useRef(null);
  const bell = useRef(null);
  const panel = useRef(null);

  useEffect(() => {
    if (busy) return;
    const controller = new AbortController();
    async function refresh() {
      try {
        const data = await api("/api/notifications", { signal: controller.signal });
        if (!controller.signal.aborted) { setFeed(data); setError(""); }
      } catch (err) { if (!controller.signal.aborted) setError(err.message); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [route, open, busy]);

  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    function outside(event) { if (!root.current?.contains(event.target)) setOpen(false); }
    function escape(event) { if (event.key === "Escape") { setOpen(false); bell.current?.focus(); } }
    function navigate() { setOpen(false); }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("hashchange", navigate);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("hashchange", navigate);
    };
  }, [open]);

  async function read(item) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await api(`/api/notifications/${item.id}/read`, { method: "POST" });
      const data = await api("/api/notifications");
      setFeed(data); setOpen(false);
      window.location.assign(item.kind === "accepted" || item.kind === "message" ? `#/app/chat/${item.request_id}` : item.kind === "declined" ? "#/app/requests/outgoing" : "#/app/requests");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function readAll() {
    if (busy || !feed.notifications.length) return;
    setBusy(true); setError("");
    try {
      await api("/api/notifications/read", json("POST", { through_id: feed.notifications[0].id }));
      setFeed(await api("/api/notifications"));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <div className="notification-root" ref={root}>
    <button className="notification-bell" type="button" aria-label={`Notifications, ${feed.unread_count} unread`} aria-expanded={open} aria-controls="notification-panel" aria-haspopup="dialog" onClick={() => setOpen(!open)} ref={bell}>
      <svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4M12 2V1" /></svg>
      {feed.unread_count > 0 && <span className="notification-count" aria-hidden="true">{feed.unread_count > 99 ? "99+" : feed.unread_count}</span>}
    </button><span className="notification-sr" role="status">{feed.unread_count} unread notifications</span>
    {open && <section className="notification-panel" id="notification-panel" role="dialog" aria-label="Notifications" tabIndex={-1} ref={panel}>
      <div className="notification-heading"><div><h2>Notifications</h2><p>{feed.unread_count ? `${feed.unread_count} unread updates` : "You're all caught up"}</p></div><button type="button" onClick={() => { setOpen(false); bell.current?.focus(); }} aria-label="Close notifications">×</button></div>
      {error && <p className="error-message" role="alert">{error}</p>}
      {loading ? <p className="notification-empty">Checking for updates...</p> : feed.notifications.length === 0 ? <p className="notification-empty">No updates yet. New requests, request decisions, and messages will appear here.</p> : <><div className="notification-tools"><span>Latest 50 updates</span><button type="button" disabled={busy || !feed.unread_count} onClick={readAll}>Mark all as read</button></div><ul className="notification-list">{feed.notifications.map((item) => <li key={item.id}><button type="button" className={item.read_at ? "notification-item" : "notification-item unread"} disabled={busy} onClick={() => read(item)}><span className="notification-dot" aria-hidden="true" /><span><strong>{describe(item)}</strong><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time>{!item.read_at && <span className="notification-sr">Unread</span>}</span><span aria-hidden="true">→</span></button></li>)}</ul></>}
    </section>}
  </div>;
}
