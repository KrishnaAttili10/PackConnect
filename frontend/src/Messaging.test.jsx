import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConnectionRequestForm, RequestInbox, Conversation } from './Messaging'
import { deferred, request, response, student } from './test/fixtures'

vi.mock('./MeetingPanel', () => ({ default: () => null }))

async function fillRequest(user) {
  await user.type(
    screen.getByRole('textbox', { name: 'Advice topic' }),
    'Projects',
  )
  await user.type(
    screen.getByRole('textbox', { name: 'Your request' }),
    'How should I prepare?',
  )
}

describe('persistent advice requests', () => {
  it('lets the sender cancel a pending request and refreshes history', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    fetch.mockResolvedValue(
      response({ request: { ...request, status: 'cancelled' } }),
    )
    render(
      <RequestInbox
        user={student}
        requests={[{ ...request, sender_id: student.id, recipient_id: 2 }]}
        loading={false}
        error=""
        onRefresh={onRefresh}
        initialTab="outgoing"
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Cancel request' }))
    expect(fetch).toHaveBeenCalledWith(
      '/api/requests/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status: 'cancelled' }),
      }),
    )
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
  })

  it('completes advice and keeps a link to saved message history', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    fetch.mockResolvedValue(
      response({ request: { ...request, status: 'completed' } }),
    )
    const props = {
      user: student,
      requests: [{ ...request, status: 'accepted' }],
      loading: false,
      error: '',
      onRefresh,
    }
    const { rerender } = render(<RequestInbox {...props} />)
    await user.click(screen.getByRole('button', { name: 'Complete advice' }))
    expect(fetch).toHaveBeenCalledWith(
      '/api/requests/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status: 'completed' }),
      }),
    )
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    rerender(
      <RequestInbox
        {...props}
        requests={[{ ...request, status: 'completed' }]}
      />,
    )
    expect(
      screen.getByRole('link', { name: 'View message history' }),
    ).toHaveAttribute('href', '#/app/chat/7')
    expect(
      screen.queryByRole('button', { name: 'Complete advice' }),
    ).not.toBeInTheDocument()
  })
  it('sends one request, disables pending controls and confirms that chat needs acceptance', async () => {
    const user = userEvent.setup()
    const pending = deferred()
    fetch.mockReturnValue(pending.promise)
    const onRequestCreated = vi.fn()
    render(
      <ConnectionRequestForm
        student={student}
        defaultCourse="CSC 510"
        onRequestCreated={onRequestCreated}
      />,
    )
    expect(screen.getByRole('button', { name: 'Send request' })).toBeDisabled()
    await fillRequest(user)
    await user.dblClick(screen.getByRole('button', { name: 'Send request' }))
    expect(screen.getByRole('button', { name: 'Sending...' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith(
      '/api/requests',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      recipient_id: 1,
      course_code: 'CSC 510',
      advice_topic: 'Projects',
      message: 'How should I prepare?',
    })
    pending.resolve(response({ request }, 201))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Chat will unlock if they accept.',
    )
    expect(onRequestCreated).toHaveBeenCalledTimes(1)
    expect(
      screen.getByRole('link', { name: 'View your requests' }),
    ).toHaveAttribute('href', '#/app/requests')
    expect(
      screen.queryByRole('link', { name: 'Open chat' }),
    ).not.toBeInTheDocument()
  })

  it('preserves the message on failure and allows retry', async () => {
    const user = userEvent.setup()
    fetch
      .mockResolvedValueOnce(
        response({ error: 'Advisor is unavailable.' }, 409),
      )
      .mockResolvedValueOnce(response({ request }, 201))
    const onRequestCreated = vi.fn()
    render(
      <ConnectionRequestForm
        student={student}
        defaultCourse="CSC 510"
        onRequestCreated={onRequestCreated}
      />,
    )
    await fillRequest(user)
    await user.click(screen.getByRole('button', { name: 'Send request' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Advisor is unavailable.',
    )
    expect(screen.getByRole('textbox', { name: 'Your request' })).toHaveValue(
      'How should I prepare?',
    )
    expect(onRequestCreated).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Send request' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Request sent')
  })

  it.each([
    ['Accept', 'accepted'],
    ['Decline', 'declined'],
  ])('persists %s and refreshes the inbox', async (action, status) => {
    const user = userEvent.setup()
    const pending = deferred()
    fetch.mockReturnValue(pending.promise)
    const onRefresh = vi.fn()
    const props = {
      user: student,
      requests: [request],
      loading: false,
      error: '',
      onRefresh,
    }
    const { rerender } = render(<RequestInbox {...props} />)
    expect(
      screen.queryByRole('link', { name: 'Open chat' }),
    ).not.toBeInTheDocument()
    await user.dblClick(screen.getByRole('button', { name: action }))
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Decline' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith(
      '/api/requests/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    )
    pending.resolve(response({ request: { ...request, status } }))
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    rerender(<RequestInbox {...props} requests={[{ ...request, status }]} />)
    if (status === 'accepted')
      expect(screen.getByRole('link', { name: 'Open chat' })).toHaveAttribute(
        'href',
        '#/app/chat/7',
      )
    else {
      expect(screen.getByText('Chat is unavailable')).toBeInTheDocument()
      expect(
        screen.queryByRole('link', { name: 'Open chat' }),
      ).not.toBeInTheDocument()
    }
    expect(
      screen.queryByRole('button', { name: 'Accept' }),
    ).not.toBeInTheDocument()
  })

  it('shows decision errors and restores action buttons', async () => {
    const user = userEvent.setup()
    fetch.mockResolvedValue(
      response({ error: 'Request is no longer pending.' }, 409),
    )
    const onRefresh = vi.fn()
    render(
      <RequestInbox
        user={student}
        requests={[request]}
        loading={false}
        error=""
        onRefresh={onRefresh}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Accept' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Request is no longer pending.',
    )
    expect(screen.getByRole('button', { name: 'Accept' })).toBeEnabled()
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('shows loading/empty states and outgoing requests without recipient controls', async () => {
    const user = userEvent.setup()
    const props = {
      user: student,
      requests: [],
      loading: true,
      error: '',
      onRefresh: vi.fn(),
    }
    const { rerender } = render(<RequestInbox {...props} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading requests...')
    rerender(
      <RequestInbox
        {...props}
        loading={false}
        requests={[{ ...request, sender_id: 1, recipient_id: 2 }]}
      />,
    )
    expect(screen.getByText(/No incoming requests yet/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Outgoing' }))
    expect(screen.getByText('Waiting for a response')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Accept' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Decline' }),
    ).not.toBeInTheDocument()
  })
})

describe('accepted-request conversation', () => {
  it('shows completed conversations as read-only while keeping their messages', async () => {
    fetch.mockResolvedValue(
      response({
        request: { ...request, status: 'completed' },
        messages: [
          {
            id: 1,
            sender_id: 2,
            body: 'Saved advice',
            created_at: request.created_at,
          },
        ],
        has_more: false,
      }),
    )
    render(<Conversation requestId={7} user={student} />)
    expect(await screen.findByText('Saved advice')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Message history is read-only',
    )
    expect(
      screen.queryByRole('button', { name: 'Send message' }),
    ).not.toBeInTheDocument()
  })
  it('loads saved history, sends once and displays the saved message', async () => {
    const user = userEvent.setup()
    const pending = deferred()
    fetch
      .mockResolvedValueOnce(
        response({
          request: { ...request, status: 'accepted' },
          messages: [
            {
              id: 1,
              sender_id: 2,
              body: 'Welcome back!',
              created_at: request.created_at,
            },
          ],
          has_more: false,
        }),
      )
      .mockReturnValueOnce(pending.promise)
    render(<Conversation requestId={7} user={student} />)
    await screen.findByRole('heading', { name: 'Chat with Sam Lee' })
    expect(screen.getByRole('log')).toHaveTextContent('Welcome back!')
    await user.type(
      screen.getByRole('textbox', { name: 'Message to Sam Lee' }),
      'Thanks for connecting!',
    )
    await user.dblClick(screen.getByRole('button', { name: 'Send message' }))
    expect(screen.getByRole('button', { name: 'Sending...' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/requests/7/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ body: 'Thanks for connecting!' }),
      }),
    )
    pending.resolve(
      response(
        {
          message: {
            id: 2,
            sender_id: 1,
            body: 'Thanks for connecting!',
            created_at: request.created_at,
          },
        },
        201,
      ),
    )
    expect(
      await screen.findByText('Thanks for connecting!'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('textbox', { name: 'Message to Sam Lee' }),
    ).toHaveValue('')
  })

  it('shows access failure without exposing a message composer', async () => {
    fetch.mockResolvedValue(
      response({ error: 'Accept this request before chatting.' }, 403),
    )
    render(<Conversation requestId={7} user={student} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Accept this request before chatting.',
    )
    expect(
      screen.queryByRole('button', { name: 'Send message' }),
    ).not.toBeInTheDocument()
  })
})
