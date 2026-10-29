import { useEffect, useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { deferred, request, response, student } from './test/fixtures'

// Keep App mounted as the real hash router does, including Cancel/Save navigation.
function Workspace({ initialRoute = 'app', onUserUpdated = () => {} }) {
  const [route, setRoute] = useState(initialRoute)
  useEffect(() => {
    const navigate = () => setRoute(window.location.hash.slice(2))
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  return (
    <App
      user={student}
      route={route}
      onLogout={() => {}}
      onUserUpdated={onUserUpdated}
    />
  )
}

beforeEach(() => {
  fetch.mockImplementation(async (url, options = {}) => {
    if (url.startsWith('/api/courses?'))
      return response({ courses: ['CSC 510', 'CSC 540'] })
    if (url.startsWith('/api/students/search?')) return response([student])
    if (url === '/api/students/1' && !options.method)
      return response({ student })
    if (url === '/api/requests') return response({ requests: [] })
    if (url === '/api/notifications')
      return response({ notifications: [], unread_count: 0 })
    throw new Error(`Unexpected API request: ${options.method || 'GET'} ${url}`)
  })
})

function holdSearch() {
  const pending = deferred()
  const normalFetch = fetch.getMockImplementation()
  fetch.mockImplementation((url, options) =>
    url.startsWith('/api/students/search?')
      ? pending.promise
      : normalFetch(url, options),
  )
  return pending
}
const writes = () =>
  fetch.mock.calls.filter(([, options]) => options?.method === 'PUT')

describe('peer search', () => {
  it('searches with the selected suggestion and preserves advanced filters', async () => {
    const user = userEvent.setup()
    render(<Workspace />)
    await screen.findByRole('heading', { name: student.name })
    await user.click(screen.getByText('Advanced filters'))
    await user.type(
      screen.getByRole('textbox', { name: 'Program' }),
      'Computer Science',
    )
    const input = screen.getByRole('combobox', { name: 'Course code' })
    await user.clear(input)
    await user.type(input, 'csc5')
    await screen.findByRole('option', { name: 'CSC 540' })
    const searches = () =>
      fetch.mock.calls.filter(([url]) =>
        url.startsWith('/api/students/search?'),
      )
    expect(searches()).toHaveLength(1)
    await user.keyboard('{ArrowUp}{Enter}')
    expect(input).toHaveValue('CSC 540')
    expect(searches()).toHaveLength(1)
    await user.keyboard('{Enter}')
    await waitFor(() => expect(searches()).toHaveLength(2))
    expect(searches()[1][0]).toBe(
      '/api/students/search?course=CSC+540&program=Computer+Science&available=true',
    )
  })

  it('shows loading, then matching peers, and submits the entered course', async () => {
    const user = userEvent.setup()
    const pending = holdSearch()
    render(<Workspace />)
    expect(screen.getByText('Searching for students...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Searching...' })).toBeDisabled()
    pending.resolve(response([student]))
    expect(
      await screen.findByRole('heading', { name: student.name }),
    ).toBeInTheDocument()
    await user.clear(screen.getByRole('combobox', { name: 'Course code' }))
    await user.type(
      screen.getByRole('combobox', { name: 'Course code' }),
      'CSC 540',
    )
    await user.click(screen.getByRole('button', { name: 'Find Students' }))
    expect(fetch).toHaveBeenCalledWith(
      '/api/students/search?course=CSC+540&available=true',
    )
  })

  it('shows an empty result after a submitted search finishes', async () => {
    const user = userEvent.setup()
    render(<Workspace />)
    await screen.findByRole('heading', { name: student.name })
    const pending = holdSearch()
    await user.click(screen.getByRole('button', { name: 'Find Students' }))
    expect(screen.getByText('Searching for students...')).toBeInTheDocument()
    pending.resolve(response([]))
    expect(
      await screen.findByText('No students found. Try another course code.'),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: student.name }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Find Students' })).toBeEnabled()
  })

  it.each(['network', 'HTTP'])(
    'shows connection feedback on %s failure and recovers on retry',
    async (failure) => {
      const user = userEvent.setup()
      const pending = holdSearch()
      render(<Workspace />)
      if (failure === 'network')
        pending.resolve(Promise.reject(new TypeError('Failed to fetch')))
      else pending.resolve(response({ error: 'Unavailable' }, 503))
      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Could not connect to the Flask backend',
      )
      fetch.mockImplementation(async (url) => {
        if (url.startsWith('/api/students/search?')) return response([student])
        if (url === '/api/requests') return response({ requests: [] })
        if (url === '/api/notifications')
          return response({ notifications: [], unread_count: 0 })
        throw new Error(`Unexpected API request: ${url}`)
      })
      await user.click(screen.getByRole('button', { name: 'Find Students' }))
      expect(
        await screen.findByRole('heading', { name: student.name }),
      ).toBeInTheDocument()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    },
  )
})

describe('profile editor', () => {
  it('persists capacity and pause settings with numeric and ISO-date values', async () => {
    const user = userEvent.setup()
    const normalFetch = fetch.getMockImplementation()
    let saved = student
    fetch.mockImplementation((url, options) => {
      if (options?.method === 'PUT') {
        saved = {
          ...student,
          ...JSON.parse(options.body),
          availability_status: 'paused',
          accepting_requests: false,
        }
        return Promise.resolve(response({ student: saved }))
      }
      if (url === '/api/students/1')
        return Promise.resolve(response({ student: saved }))
      return normalFetch(url, options)
    })
    render(<Workspace initialRoute="app/profile/edit" />)
    const limit = await screen.findByRole('spinbutton', {
      name: 'Maximum open advice requests',
    })
    await user.clear(limit)
    await user.type(limit, '2')
    fireEvent.change(screen.getByLabelText('Pause new requests until'), {
      target: { value: '2027-01-15' },
    })
    await user.click(screen.getByRole('button', { name: 'Save Profile' }))
    expect(JSON.parse(writes()[0][1].body)).toMatchObject({
      max_open_requests: 2,
      pause_until: '2027-01-15',
    })
    expect(
      await screen.findByText('Paused until Jan 15, 2027 (Eastern time)'),
    ).toBeInTheDocument()
  })

  it('clears a pause and saves an unlimited request capacity', async () => {
    const user = userEvent.setup()
    const normalFetch = fetch.getMockImplementation()
    let saved = { ...student, pause_until: '2027-01-15' }
    fetch.mockImplementation((url, options) => {
      if (options?.method === 'PUT') {
        saved = { ...student, ...JSON.parse(options.body) }
        return Promise.resolve(response({ student: saved }))
      }
      if (url === '/api/students/1')
        return Promise.resolve(response({ student: saved }))
      return normalFetch(url, options)
    })
    render(<Workspace initialRoute="app/profile/edit" />)
    await user.clear(
      await screen.findByRole('spinbutton', {
        name: 'Maximum open advice requests',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Clear pause' }))
    await user.click(screen.getByRole('button', { name: 'Save Profile' }))
    expect(JSON.parse(writes()[0][1].body)).toMatchObject({
      max_open_requests: null,
      pause_until: null,
    })
    expect(await screen.findByText('No request limit')).toBeInTheDocument()
  })

  it('saves edited fields and prevents duplicate submissions while saving', async () => {
    const user = userEvent.setup()
    const pending = deferred()
    const normalFetch = fetch.getMockImplementation()
    const updated = {
      ...student,
      bio: 'Updated bio',
      completed_courses: ['CSC 510', 'CSC 540'],
    }
    fetch.mockImplementation((url, options) =>
      options?.method === 'PUT' ? pending.promise : normalFetch(url, options),
    )
    const onUserUpdated = vi.fn()
    render(
      <Workspace
        initialRoute="app/profile/edit"
        onUserUpdated={onUserUpdated}
      />,
    )
    const bio = await screen.findByRole('textbox', { name: 'Bio' })
    expect(bio).toHaveValue(student.bio)
    await user.clear(bio)
    await user.type(bio, 'Updated bio')
    await user.clear(screen.getByRole('textbox', { name: 'Completed courses' }))
    await user.type(
      screen.getByRole('textbox', { name: 'Completed courses' }),
      'CSC 510, CSC 540, ',
    )
    await user.dblClick(screen.getByRole('button', { name: 'Save Profile' }))
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(writes()).toHaveLength(1)
    expect(writes()[0][0]).toBe('/api/students/1')
    expect(JSON.parse(writes()[0][1].body)).toMatchObject({
      bio: updated.bio,
      completed_courses: updated.completed_courses,
    })
    pending.resolve(response({ student: updated }))
    await waitFor(() => expect(onUserUpdated).toHaveBeenCalledWith(updated))
    await waitFor(() => expect(window.location.hash).toBe('#/app/profile'))
    expect(await screen.findByText('Profile updated.')).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Save Profile' }),
      ).not.toBeInTheDocument(),
    )
  })

  it('discards cancelled edits and restores saved values when reopened', async () => {
    const user = userEvent.setup()
    render(<Workspace initialRoute="app/profile/edit" />)
    const bio = await screen.findByRole('textbox', { name: 'Bio' })
    await user.clear(bio)
    await user.type(bio, 'Unsaved change')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(window.location.hash).toBe('#/app/profile'))
    await user.click(
      await screen.findByRole('button', { name: 'Edit Profile' }),
    )
    expect(await screen.findByRole('textbox', { name: 'Bio' })).toHaveValue(
      student.bio,
    )
    expect(writes()).toHaveLength(0)
  })

  it('keeps edits after an API failure and enables retry', async () => {
    const user = userEvent.setup()
    const normalFetch = fetch.getMockImplementation()
    fetch.mockImplementation((url, options) =>
      options?.method === 'PUT'
        ? Promise.resolve(
            response({ error: 'Session expired. Sign in again.' }, 401),
          )
        : normalFetch(url, options),
    )
    const onUserUpdated = vi.fn()
    render(
      <Workspace
        initialRoute="app/profile/edit"
        onUserUpdated={onUserUpdated}
      />,
    )
    const bio = await screen.findByRole('textbox', { name: 'Bio' })
    await user.type(bio, ' More details.')
    await user.click(screen.getByRole('button', { name: 'Save Profile' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Session expired. Sign in again.',
    )
    expect(bio).toHaveValue(`${student.bio} More details.`)
    expect(screen.getByRole('button', { name: 'Save Profile' })).toBeEnabled()
    expect(onUserUpdated).not.toHaveBeenCalled()
  })
})

describe('peer profile request controls', () => {
  it.each([
    ['paused', '2027-01-15', 'Paused until Jan 15, 2027 (Eastern time)'],
    ['at_capacity', null, 'At capacity — not accepting new requests'],
  ])(
    'shows %s availability and prevents a new request',
    async (status, until, label) => {
      const normalFetch = fetch.getMockImplementation()
      const peer = {
        ...student,
        id: 2,
        accepting_requests: false,
        availability_status: status,
        pause_until: until,
        max_open_requests: 2,
        open_request_count: 2,
      }
      fetch.mockImplementation((url, options) =>
        url === '/api/students/2'
          ? Promise.resolve(response({ student: peer }))
          : normalFetch(url, options),
      )
      render(<Workspace initialRoute="app/students/2" />)
      expect(await screen.findByText(label)).toBeInTheDocument()
      expect(screen.getByText('2 of 2 advice slots in use')).toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'Send request' }),
      ).not.toBeInTheDocument()
    },
  )

  it('preserves chat access when an existing advisor is paused or full', async () => {
    const normalFetch = fetch.getMockImplementation()
    fetch.mockImplementation((url, options) => {
      if (url === '/api/students/2')
        return Promise.resolve(
          response({
            student: {
              ...student,
              id: 2,
              accepting_requests: false,
              availability_status: 'at_capacity',
            },
          }),
        )
      if (url === '/api/requests')
        return Promise.resolve(
          response({ requests: [{ ...request, status: 'accepted' }] }),
        )
      return normalFetch(url, options)
    })
    render(<Workspace initialRoute="app/students/2" />)
    expect(
      await screen.findByRole('link', { name: 'Open chat' }),
    ).toHaveAttribute('href', '#/app/chat/7')
  })

  it('permits a new request after a previous connection was completed', async () => {
    const normalFetch = fetch.getMockImplementation()
    fetch.mockImplementation((url, options) => {
      if (url === '/api/students/2')
        return Promise.resolve(response({ student: { ...student, id: 2 } }))
      if (url === '/api/requests')
        return Promise.resolve(
          response({ requests: [{ ...request, status: 'completed' }] }),
        )
      return normalFetch(url, options)
    })
    render(<Workspace initialRoute="app/students/2" />)
    expect(
      await screen.findByRole('button', { name: 'Send request' }),
    ).toBeInTheDocument()
  })

  it('lets a student send a request to a registered advisor', async () => {
    const user = userEvent.setup()
    const peer = { ...student, id: 2, name: 'Registered Advisor' }
    const normalFetch = fetch.getMockImplementation()
    fetch.mockImplementation((url, options) => {
      if (url === '/api/students/2')
        return Promise.resolve(response({ student: peer }))
      if (url === '/api/requests' && options?.method === 'POST')
        return Promise.resolve(response({ request: { id: 7 } }, 201))
      return normalFetch(url, options)
    })
    render(<Workspace initialRoute="app/students/2" />)
    await user.type(
      await screen.findByRole('textbox', { name: 'Advice topic' }),
      'Projects',
    )
    await user.type(
      screen.getByRole('textbox', { name: 'Your request' }),
      'How should I prepare?',
    )
    await user.click(screen.getByRole('button', { name: 'Send request' }))
    expect(
      await screen.findByText(/Request sent to Registered Advisor/),
    ).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith(
      '/api/requests',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          course_code: 'CSC 510',
          advice_topic: 'Projects',
          message: 'How should I prepare?',
          recipient_id: 2,
        }),
      }),
    )
  })

  it('explains why an old direct link to an unregistered profile cannot receive requests', async () => {
    const normalFetch = fetch.getMockImplementation()
    fetch.mockImplementation((url, options) =>
      url === '/api/students/2'
        ? Promise.resolve(
            response({
              student: { ...student, id: 2, can_receive_requests: false },
            }),
          )
        : normalFetch(url, options),
    )
    render(<Workspace initialRoute="app/students/2" />)
    expect(
      await screen.findByText(/This sample profile has no registered account/),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Send request' }),
    ).not.toBeInTheDocument()
  })
})
