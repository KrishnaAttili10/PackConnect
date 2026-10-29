import { useEffect, useState } from 'react'
import { api, json } from './messagingApi'

export default function MeetingPanel({ requestId, user, active }) {
  const [meetings, setMeetings] = useState([])
  const [form, setForm] = useState({ start: '', duration: '30', location: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let timer
    async function load() {
      try {
        const data = await api(`/api/requests/${requestId}/meetings`, {
          signal: controller.signal,
        })
        if (!controller.signal.aborted) setMeetings(data.meetings)
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message)
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 10000)
      }
    }
    load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [requestId, version])
  async function act(id, status) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (id)
        await api(
          `/api/requests/${requestId}/meetings/${id}`,
          json('PATCH', { status }),
        )
      else {
        const start = new Date(form.start)
        await api(
          `/api/requests/${requestId}/meetings`,
          json('POST', {
            starts_at: start.toISOString(),
            ends_at: new Date(
              start.getTime() + Number(form.duration) * 60000,
            ).toISOString(),
            location: form.location,
          }),
        )
        setForm({ start: '', duration: '30', location: '' })
      }
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="meeting-panel">
      <h3>Advice meetings</h3>
      {error && <p role="alert">{error}</p>}
      {meetings.map((item) => (
        <article className="request-card" key={item.id}>
          <div>
            <p>
              <time dateTime={item.starts_at}>
                {new Date(item.starts_at).toLocaleString()}
              </time>{' '}
              – {new Date(item.ends_at).toLocaleTimeString()}
            </p>
            <p className="preserve-lines">{item.location}</p>
            <p>Status: {item.status}</p>
            {item.status === 'proposed' &&
              active &&
              item.proposer_id !== user.id && (
                <>
                  <button
                    disabled={busy}
                    onClick={() => act(item.id, 'accepted')}
                  >
                    Accept meeting
                  </button>{' '}
                  <button
                    disabled={busy}
                    onClick={() => act(item.id, 'declined')}
                  >
                    Decline meeting
                  </button>
                </>
              )}
            {['proposed', 'accepted'].includes(item.status) && (
              <button disabled={busy} onClick={() => act(item.id, 'cancelled')}>
                Cancel meeting
              </button>
            )}
            {item.status === 'accepted' && (
              <a
                href={`/api/requests/${requestId}/meetings/${item.id}/calendar.ics`}
              >
                Download calendar event
              </a>
            )}
          </div>
        </article>
      ))}
      {active && (
        <form
          className="request-fields"
          onSubmit={(e) => {
            e.preventDefault()
            act()
          }}
        >
          <fieldset disabled={busy}>
            <legend>Propose a meeting</legend>
            <p>
              Times use your device’s time zone:{' '}
              {Intl.DateTimeFormat().resolvedOptions().timeZone}. The other
              student must accept.
            </p>
            <label>
              Meeting date and time
              <input
                aria-label="Meeting date and time"
                type="datetime-local"
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
                required
              />
            </label>
            <label>
              Duration (minutes)
              <input
                aria-label="Duration (minutes)"
                type="number"
                min="15"
                max="120"
                value={form.duration}
                onChange={(e) => setForm({ ...form, duration: e.target.value })}
                required
              />
            </label>
            <label>
              Meeting location or link
              <input
                aria-label="Meeting location or link"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                maxLength={300}
                required
              />
            </label>
            <button disabled={busy}>
              {busy ? 'Saving…' : 'Propose meeting'}
            </button>
          </fieldset>
        </form>
      )}
    </section>
  )
}
