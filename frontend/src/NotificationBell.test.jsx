import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import NotificationBell from './NotificationBell'
import { deferred, response } from './test/fixtures'

const item = {
  id: 12,
  request_id: 7,
  kind: 'request_received',
  actor_name: 'Sam Lee',
  course_code: 'CSC 510',
  read_at: null,
  created_at: '2026-10-28T12:00:00Z',
}
const feed = { notifications: [item], unread_count: 63 }
const gets = () =>
  fetch.mock.calls.filter(([, options]) => options?.method !== 'POST')
const writes = () =>
  fetch.mock.calls.filter(([, options]) => options?.method === 'POST')

async function open(user) {
  render(<NotificationBell route="app" />)
  await user.click(
    await screen.findByRole('button', { name: 'Notifications, 63 unread' }),
  )
  await waitFor(() => expect(gets()).toHaveLength(2))
}

describe('notification read actions', () => {
  it('clears the badge immediately, sends once, and does not refetch on success', async () => {
    const pending = deferred()
    fetch.mockImplementation((url, options) =>
      options?.method === 'POST'
        ? pending.promise
        : Promise.resolve(response(feed)),
    )
    const user = userEvent.setup()
    await open(user)
    await user.dblClick(
      screen.getByRole('button', { name: 'Mark all as read' }),
    )
    expect(
      screen.getByRole('button', { name: 'Notifications, 0 unread' }),
    ).toBeInTheDocument()
    expect(document.querySelector('.notification-item.unread')).toBeNull()
    expect(writes()).toHaveLength(1)
    expect(writes()[0]).toEqual([
      '/api/notifications/read',
      expect.objectContaining({ body: JSON.stringify({ through_id: 12 }) }),
    ])
    await act(async () =>
      pending.resolve(response({ status: 'ok', unread_count: 0 })),
    )
    expect(gets()).toHaveLength(2)
  })

  it.each(['HTTP', 'network'])(
    'restores unread state on %s failure and permits retry',
    async (failure) => {
      const pending = deferred()
      fetch.mockImplementation((url, options) =>
        options?.method === 'POST'
          ? pending.promise
          : Promise.resolve(response(feed)),
      )
      const user = userEvent.setup()
      await open(user)
      fireEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))
      if (failure === 'HTTP')
        await act(async () =>
          pending.resolve(
            response({ error: 'Unable to save read status' }, 503),
          ),
        )
      else
        await act(async () =>
          pending.resolve(Promise.reject(new TypeError('Network offline'))),
        )
      expect(await screen.findByRole('alert')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Notifications, 63 unread' }),
      ).toBeInTheDocument()
      expect(document.querySelector('.notification-item.unread')).not.toBeNull()
      fetch.mockImplementation((url, options) =>
        Promise.resolve(
          response(options?.method === 'POST' ? { unread_count: 0 } : feed),
        ),
      )
      await user.click(screen.getByRole('button', { name: 'Mark all as read' }))
      await waitFor(() =>
        expect(screen.queryByRole('alert')).not.toBeInTheDocument(),
      )
      expect(
        screen.getByRole('button', { name: 'Notifications, 0 unread' }),
      ).toBeInTheDocument()
      expect(writes()).toHaveLength(2)
    },
  )

  it('ignores a stale refresh and retains the server count for newer arrivals', async () => {
    const old = deferred()
    const save = deferred()
    fetch.mockImplementation((url, options) => {
      if (options?.method === 'POST') return save.promise
      return gets().length === 1 ? Promise.resolve(response(feed)) : old.promise
    })
    const user = userEvent.setup()
    await open(user)
    const signal = gets()[1][1].signal
    await user.click(screen.getByRole('button', { name: 'Mark all as read' }))
    expect(signal.aborted).toBe(true)
    await act(async () => old.resolve(response(feed)))
    expect(
      screen.getByRole('button', { name: 'Notifications, 0 unread' }),
    ).toBeInTheDocument()
    await act(async () => save.resolve(response({ unread_count: 1 })))
    expect(
      screen.getByRole('button', { name: 'Notifications, 1 unread' }),
    ).toBeInTheDocument()
    expect(gets()).toHaveLength(2)
  })

  it('picks up newer notifications on the next regular poll without clearing them', async () => {
    vi.useFakeTimers()
    try {
      fetch.mockResolvedValue(response(feed))
      render(<NotificationBell route="app" />)
      await act(() => vi.advanceTimersByTimeAsync(0))
      fireEvent.click(
        screen.getByRole('button', { name: 'Notifications, 63 unread' }),
      )
      await act(async () => {})
      const save = deferred()
      fetch.mockImplementation((url, options) =>
        options?.method === 'POST'
          ? save.promise
          : Promise.resolve(
              response({
                notifications: [
                  { ...item, id: 13 },
                  { ...item, read_at: '2026-10-28T13:00:00Z' },
                ],
                unread_count: 1,
              }),
            ),
      )
      fireEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))
      await act(() => vi.advanceTimersByTimeAsync(10000))
      expect(gets()).toHaveLength(2)
      await act(async () => save.resolve(response({ unread_count: 1 })))
      await act(() => vi.advanceTimersByTimeAsync(5000))
      expect(gets()).toHaveLength(3)
      expect(
        screen.getByRole('button', { name: 'Notifications, 1 unread' }),
      ).toBeInTheDocument()
      expect(
        document.querySelectorAll('.notification-item.unread'),
      ).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
