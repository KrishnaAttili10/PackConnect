import { useEffect, useId, useRef, useState } from 'react'
import './CourseAutocomplete.css'

export default function CourseAutocomplete({ value, onChange }) {
  const id = useId()
  const list = useRef(null)
  const [focused, setFocused] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [result, setResult] = useState({
    query: '',
    courses: [],
    failed: false,
  })
  const [active, setActive] = useState(-1)
  const query = value.trim()
  const current = result.query === query
  const courses = current ? result.courses : []
  const open = focused && !dismissed && Boolean(query)

  useEffect(() => {
    if (open && active >= 0) {
      list.current?.children[active]?.scrollIntoView?.({ block: 'nearest' })
    }
  }, [open, active])

  useEffect(() => {
    if (!focused || dismissed || !query) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(
          `/api/courses?q=${encodeURIComponent(query)}`,
          {
            signal: controller.signal,
          },
        )
        if (!response.ok) throw new Error('Unable to load courses')
        const data = await response.json()
        if (
          !Array.isArray(data?.courses) ||
          data.courses.some((code) => typeof code !== 'string')
        ) {
          throw new Error('Invalid course suggestions')
        }
        if (!controller.signal.aborted) {
          setResult({ query, courses: data.courses, failed: false })
        }
      } catch {
        if (!controller.signal.aborted) {
          setResult({ query, courses: [], failed: true })
        }
      }
    }, 200)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, focused, dismissed])

  function select(code) {
    onChange(code)
    setDismissed(true)
    setActive(-1)
  }

  return (
    <div className="course-autocomplete">
      <input
        type="text"
        role="combobox"
        aria-label="Course code"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined}
        aria-activedescendant={
          open && courses[active] ? `${id}-${active}` : undefined
        }
        aria-describedby={`${id}-hint`}
        autoComplete="off"
        maxLength={30}
        value={value}
        placeholder="Enter a course code, e.g. CSC 510"
        onChange={(event) => {
          onChange(event.target.value)
          setActive(-1)
          setDismissed(false)
        }}
        onFocus={() => {
          setFocused(true)
          setDismissed(false)
        }}
        onBlur={() => {
          setFocused(false)
          setActive(-1)
        }}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return
          if (event.key === 'Escape') {
            event.preventDefault()
            setDismissed(true)
            setActive(-1)
          } else if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
            event.preventDefault()
            setDismissed(false)
            if (courses.length) {
              setActive((previous) =>
                event.key === 'ArrowDown'
                  ? (previous + 1) % courses.length
                  : (previous <= 0 ? courses.length : previous) - 1,
              )
            }
          } else if (event.key === 'Enter' && open && courses[active]) {
            event.preventDefault()
            select(courses[active])
          } else if (event.key === 'Enter') {
            setDismissed(true)
          }
        }}
      />
      <span className="course-hint" id={`${id}-hint`}>
        Suggestions come from peers’ completed courses. You can also enter a
        code.
      </span>
      {open && (
        <div className="course-suggestions">
          <ul
            ref={list}
            role="listbox"
            aria-label="Course suggestions"
            id={`${id}-list`}
          >
            {courses.map((code, index) => (
              <li
                key={code}
                id={`${id}-${index}`}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => select(code)}
              >
                {code}
              </li>
            ))}
          </ul>
          {!courses.length && (
            <p role="status">
              {!current
                ? 'Looking up courses…'
                : result.failed
                  ? 'Suggestions unavailable. You can still search by course code.'
                  : 'No matching courses yet. You can still search by course code.'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
