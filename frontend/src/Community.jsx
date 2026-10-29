import { useEffect, useState } from 'react'
import { api, json } from './messagingApi'

function useList(path, field) {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let timer
    async function load() {
      try {
        const data = await api(path, { signal: controller.signal })
        if (!controller.signal.aborted) {
          setItems(data[field])
          setError('')
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message)
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
          timer = setTimeout(load, 8000)
        }
      }
    }
    load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [path, field, version])
  return { items, error, loading, refresh: () => setVersion((v) => v + 1) }
}

export function ConversationInbox() {
  const { items, error, loading } = useList(
    '/api/conversations',
    'conversations',
  )
  return (
    <section className="request-panel">
      <h2>Conversations</h2>
      {error && <p role="alert">{error}</p>}
      {loading ? (
        <p role="status">Loading conversations…</p>
      ) : !items.length ? (
        <p>No conversations yet. Accept an advice request to start chatting.</p>
      ) : (
        <div className="request-list">
          {items.map((item) => (
            <article className="request-card" key={item.id}>
              <div>
                <a href={`#/app/chat/${item.id}`}>
                  <strong>{item.peer_name}</strong>
                </a>
                <p>
                  {item.course_code} · {item.advice_topic}
                </p>
                <p className="preserve-lines">
                  {item.latest_message || 'Start the conversation.'}
                </p>
                <time dateTime={item.updated_at}>
                  {new Date(item.updated_at).toLocaleString()}
                </time>
                <span className={`status-badge ${item.status}`}>
                  {item.status}
                </span>
              </div>
              {Number(item.unread_count) > 0 && (
                <span className="available-badge">
                  {item.unread_count} unread
                </span>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export function ReportForm({ studentId, messageId, onClose }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api(
        `/api/students/${studentId}/reports`,
        json('POST', {
          reason,
          ...(messageId ? { message_id: messageId } : {}),
        }),
      )
      setSent(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="request-form" onSubmit={submit}>
      <h3>{messageId ? 'Report this message' : 'Report this student'}</h3>
      {sent ? (
        <p role="status">Report submitted for moderator review.</p>
      ) : (
        <>
          <label>
            Describe your concern
            <textarea
              aria-label="Report reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
              required
              disabled={busy}
            />
          </label>
          <button disabled={busy || !reason.trim()}>
            {busy ? 'Submitting…' : 'Submit report'}
          </button>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <button type="button" onClick={onClose} disabled={busy}>
        Close report
      </button>
    </form>
  )
}

export function SafetyControls({ student, onChanged }) {
  const [reporting, setReporting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function toggle() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api(`/api/students/${student.id}/block`, {
        method: student.blocked_by_me ? 'DELETE' : 'POST',
      })
      await onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="safety-controls">
      <h3>Contact controls</h3>
      <p>
        Blocking stops new requests, messages, and meetings, and closes existing
        connections. Message history stays available.
      </p>
      <button type="button" onClick={toggle} disabled={busy}>
        {busy
          ? 'Saving…'
          : student.blocked_by_me
            ? 'Unblock student'
            : 'Block student'}
      </button>{' '}
      <button type="button" onClick={() => setReporting(!reporting)}>
        Report student
      </button>
      {error && <p role="alert">{error}</p>}
      {reporting && (
        <ReportForm
          studentId={student.id}
          onClose={() => setReporting(false)}
        />
      )}
    </section>
  )
}

export function BlockedStudents() {
  const { items, error, loading, refresh } = useList('/api/blocks', 'blocks')
  const [busy, setBusy] = useState(null)
  const [actionError, setActionError] = useState('')
  async function unblock(id) {
    if (busy !== null) return
    setBusy(id)
    setActionError('')
    try {
      await api(`/api/students/${id}/block`, { method: 'DELETE' })
      refresh()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(null)
    }
  }
  return (
    <section className="request-panel">
      <h2>Blocked students</h2>
      {(error || actionError) && <p role="alert">{actionError || error}</p>}
      {loading ? (
        <p role="status">Loading blocked students…</p>
      ) : !items.length ? (
        <p>You have not blocked anyone.</p>
      ) : (
        items.map((item) => (
          <article className="request-card" key={item.id}>
            <a href={`#/app/students/${item.id}`}>{item.name}</a>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => unblock(item.id)}
            >
              Unblock {item.name}
            </button>
          </article>
        ))
      )}
    </section>
  )
}

export function Moderation() {
  const { items, error, loading, refresh } = useList(
    '/api/moderation/reports',
    'reports',
  )
  const [busy, setBusy] = useState(null)
  const [resolutions, setResolutions] = useState({})
  const [actionError, setActionError] = useState('')
  async function review(id, status) {
    if (busy !== null) return
    setBusy(id)
    setActionError('')
    try {
      await api(
        `/api/moderation/reports/${id}`,
        json('PATCH', { status, resolution: resolutions[id] || '' }),
      )
      refresh()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(null)
    }
  }
  return (
    <section className="request-panel">
      <h2>Report review</h2>
      {(error || actionError) && <p role="alert">{actionError || error}</p>}
      {loading ? (
        <p role="status">Loading reports…</p>
      ) : !items.length ? (
        <p>No reports to review.</p>
      ) : (
        items.map((item) => (
          <article className="request-card" key={item.id}>
            <div>
              <h3>
                {item.reporter_name} reported {item.reported_name}
              </h3>
              <p className="preserve-lines">{item.reason}</p>
              {item.message_body && (
                <blockquote className="preserve-lines">
                  {item.message_body}
                </blockquote>
              )}
              <p>Status: {item.status}</p>
              {item.status === 'open' ? (
                <>
                  <label>
                    Resolution
                    <textarea
                      aria-label={`Resolution for report ${item.id}`}
                      value={resolutions[item.id] || ''}
                      onChange={(e) =>
                        setResolutions({
                          ...resolutions,
                          [item.id]: e.target.value,
                        })
                      }
                      maxLength={2000}
                    />
                  </label>
                  <button
                    disabled={busy !== null || !resolutions[item.id]?.trim()}
                    onClick={() => review(item.id, 'resolved')}
                  >
                    Resolve report {item.id}
                  </button>{' '}
                  <button
                    disabled={busy !== null || !resolutions[item.id]?.trim()}
                    onClick={() => review(item.id, 'dismissed')}
                  >
                    Dismiss report {item.id}
                  </button>
                </>
              ) : (
                <p>{item.resolution}</p>
              )}
            </div>
          </article>
        ))
      )}
    </section>
  )
}
