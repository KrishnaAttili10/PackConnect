# Course autocomplete

The peer-search course field suggests codes from registered students' completed
courses. It is not an official university catalog and does not supply course
titles or verify completion. Current courses and profiles without a registered
account are excluded. Confirmed, linked Supabase users are included before their
first app login. Courses from advisors who paused advising can still appear;
the search's availability filter determines which peers are returned.

`GET /api/courses?q=CSC5` returns a `courses` array containing up to ten distinct,
alphabetically sorted codes. Matching ignores case, whitespace, and hyphens and
treats the prefix literally, including SQL wildcard characters. Missing/blank
queries and normalized queries longer than 30 characters return an empty array.
Student search uses the same normalization, including for existing course rows.
No schema migration is required.

The field waits 200 ms after typing before requesting suggestions and cancels
outdated requests. Arrow keys highlight options; Enter selects the highlighted
code without submitting the form. Enter again submits the search. Escape, blur,
or selection closes the list. Highlighted options scroll into view. Manual entry
remains available when no suggestion matches or the API fails or returns an
invalid response.

## Automated verification

From `frontend/`, run `npm test`, `npm run lint`, `npm run build`, and
`npx prettier --check "src/**/*.{js,jsx,ts,tsx,css,json}"`.

From the repository root, run the backend suite with a dedicated local database
as described in [Supabase verification](SUPABASE.md#verification).

Coverage includes keyboard selection and wrapping, scrolling, mouse selection,
Escape and blur, manual-search fallbacks, malformed API data, debouncing,
cancellation and stale responses, selection with advanced filters, normalization,
deduplication, result limits, literal prefixes, registered-account eligibility,
Supabase email confirmation, and suggestions changing after profile edits.

## Browser acceptance check

Use two fictional accounts: an advisor with several completed courses and a
student looking for advice.

1. Sign in as the student, enter a partial course code, and confirm suggestions.
2. Use ArrowUp to highlight the final suggestion; confirm it scrolls into view.
3. Press Enter to select it, then Enter again to search and find the advisor.
4. Search a manual code such as `csc-510`; confirm it finds `CSC 510` peers.
5. Repeat at a narrow mobile viewport; tap a suggestion and check that the page
   has no horizontal overflow.
6. Check that Escape and clicking elsewhere close the dropdown, and that typing
   an unknown code still permits manual search.

On October 28, 2026, local verification passed 30 frontend tests and 94 backend
tests, with two opt-in live Supabase tests skipped. Lint, formatting, and the
production build passed. Headless Chrome checked the production build against
Flask and isolated PostgreSQL at desktop and mobile sizes: suggestions, keyboard
scrolling/selection, normalized manual search, touch selection, and horizontal
overflow checks passed without JavaScript exceptions. Live Supabase data was not
used for these checks.
