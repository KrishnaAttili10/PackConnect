import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import CourseAutocomplete from './CourseAutocomplete'
import { deferred, response } from './test/fixtures'

function Search({ onSubmit = () => {} }) {
  const [value, setValue] = useState('')
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(value)
      }}
    >
      <CourseAutocomplete value={value} onChange={setValue} />
      <button>Search</button>
    </form>
  )
}

describe('course autocomplete', () => {
  it('keeps keyboard-highlighted options visible in a long suggestion list', async () => {
    fetch.mockResolvedValue(
      response({
        courses: Array.from({ length: 10 }, (_, i) => `CSC ${510 + i}`),
      }),
    )
    const user = userEvent.setup()
    render(<Search />)
    await user.type(screen.getByRole('combobox'), 'CSC')
    const last = await screen.findByRole('option', { name: 'CSC 519' })
    last.scrollIntoView = vi.fn()
    await user.keyboard('{ArrowUp}')
    expect(last).toHaveAttribute('aria-selected', 'true')
    expect(last.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' })
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('option', { name: 'CSC 510' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it.each([{}, { courses: null }, { courses: [510] }])(
    'handles malformed suggestion data without interrupting manual search: %j',
    async (data) => {
      fetch.mockResolvedValue(response(data))
      const user = userEvent.setup()
      const submit = vi.fn()
      render(<Search onSubmit={submit} />)
      await user.type(screen.getByRole('combobox'), 'CSC510')
      expect(
        await screen.findByText(
          'Suggestions unavailable. You can still search by course code.',
        ),
      ).toBeInTheDocument()
      await user.keyboard('{Enter}')
      expect(submit).toHaveBeenCalledWith('CSC510')
    },
  )

  it('selects with arrows and Enter without prematurely submitting the search', async () => {
    fetch.mockResolvedValue(response({ courses: ['CSC 510', 'CSC 540'] }))
    const submit = vi.fn()
    const user = userEvent.setup()
    render(<Search onSubmit={submit} />)
    const input = screen.getByRole('combobox')
    await user.type(input, 'csc')
    await screen.findByRole('option', { name: 'CSC 510' })
    await user.keyboard('{ArrowDown}{ArrowDown}')
    expect(screen.getByRole('option', { name: 'CSC 540' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(input).toHaveAttribute(
      'aria-activedescendant',
      screen.getByRole('option', { name: 'CSC 540' }).id,
    )
    await user.keyboard('{Enter}')
    expect(input).toHaveValue('CSC 540')
    expect(input).toHaveAttribute('aria-expanded', 'false')
    expect(submit).not.toHaveBeenCalled()
    await user.keyboard('{Enter}')
    expect(submit).toHaveBeenCalledWith('CSC 540')
  })

  it('supports pointer selection and dismisses on Escape or blur', async () => {
    fetch.mockResolvedValue(response({ courses: ['CSC 510'] }))
    const user = userEvent.setup()
    render(<Search />)
    const input = screen.getByRole('combobox')
    await user.type(input, 'CSC')
    await user.click(await screen.findByRole('option', { name: 'CSC 510' }))
    expect(input).toHaveValue('CSC 510')
    expect(input).toHaveFocus()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await user.type(input, ' ')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await user.tab()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it.each(['empty', 'failure'])(
    'preserves manual searches when suggestions are %s',
    async (state) => {
      fetch.mockResolvedValue(
        state === 'empty' ? response({ courses: [] }) : response({}, 503),
      )
      const user = userEvent.setup()
      const submit = vi.fn()
      render(<Search onSubmit={submit} />)
      await user.type(screen.getByRole('combobox'), 'XYZ999')
      expect(
        await screen.findByText(/You can still search by course code/),
      ).toBeInTheDocument()
      await user.keyboard('{Enter}')
      expect(submit).toHaveBeenCalledWith('XYZ999')
    },
  )

  it('debounces queries and ignores stale responses after typing or clearing', async () => {
    vi.useFakeTimers()
    try {
      const old = deferred()
      fetch
        .mockReturnValueOnce(old.promise)
        .mockResolvedValue(response({ courses: ['ECE 200'] }))
      render(<Search />)
      const input = screen.getByRole('combobox')
      fireEvent.focus(input)
      fireEvent.change(input, { target: { value: 'C' } })
      fireEvent.change(input, { target: { value: 'CSC' } })
      expect(fetch).not.toHaveBeenCalled()
      await act(() => vi.advanceTimersByTimeAsync(200))
      expect(fetch).toHaveBeenCalledTimes(1)
      const signal = fetch.mock.calls[0][1].signal
      fireEvent.change(input, { target: { value: 'ECE' } })
      expect(signal.aborted).toBe(true)
      await act(() => vi.advanceTimersByTimeAsync(200))
      expect(
        screen.getByRole('option', { name: 'ECE 200' }),
      ).toBeInTheDocument()
      await act(async () => old.resolve(response({ courses: ['CSC 510'] })))
      expect(
        screen.queryByRole('option', { name: 'CSC 510' }),
      ).not.toBeInTheDocument()
      fireEvent.change(input, { target: { value: '' } })
      await act(() => vi.advanceTimersByTimeAsync(300))
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      expect(fetch).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('aborts pending suggestions when unmounted', async () => {
    fetch.mockReturnValue(deferred().promise)
    const user = userEvent.setup()
    const { unmount } = render(<Search />)
    await user.type(screen.getByRole('combobox'), 'CSC')
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    const signal = fetch.mock.calls[0][1].signal
    unmount()
    expect(signal.aborted).toBe(true)
  })
})
