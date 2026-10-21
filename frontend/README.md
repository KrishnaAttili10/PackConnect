# PackConnect frontend

React + Vite serves the student workspace. From this directory, use Node.js 24
and install the locked dependencies with `npm ci`.

```sh
npm run dev        # local UI; /api proxies to Flask on port 5000
npm test           # all frontend interaction tests, once; fails on test failures
npm run test:watch # rerun affected tests during development
npm run lint
npm run build
```

## Interaction tests (issue #10)

Vitest runs React Testing Library and user-event in jsdom. Tests interact through
visible labels, buttons, and messages, and assert the outgoing API payloads.

| Test file | Scenarios |
| --- | --- |
| `src/RegistrationForm.test.jsx` | Registration success, duplicate-submit prevention, API error feedback, retained inputs, retry, return to sign in |
| `src/App.test.jsx` | Search loading, populated and empty results, network/HTTP failures and recovery; profile edits, saved payload, cancellation and reopening, duplicate-submit prevention, API failure |
| `src/Messaging.test.jsx` | Advice request creation, waiting for acceptance, errors and retry; incoming accept/decline, outgoing restrictions, loading/empty inbox; accepted chat send and denied access |

`src/test/fixtures.js` supplies fictional students, requests, fixed timestamps,
and manually resolved promises. Each test mocks `fetch`; the shared setup
rejects unconfigured requests, so the suite never calls real services. Deferred
responses keep loading/saving states observable without arbitrary sleeps.
Components, DOM, fetch stubs, hash navigation, and polling timers are cleaned up
between tests. No running Flask server, database, secrets, or network connection
is required after installing dependencies.

The workspace tests keep the real App and its child components mounted and use
a small hash-navigation harness to exercise Save/Cancel navigation. Inbox tests
supply refreshed server records through props after checking the PATCH request.
These are component interaction tests; server authorization and database
persistence remain covered by backend tests. Browser layout and full end-to-end
flows are outside this suite.

GitHub Actions runs `npm test` in the frontend job of
[the quality workflow](../.github/workflows/ci.yml), alongside lint and build.
