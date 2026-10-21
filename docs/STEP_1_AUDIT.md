# Step 1: PackConnect baseline audit

Audit date: October 20, 2026 (America/New_York).
Application revision inspected: `f1885bd`.

This is a local code and API audit, not a completed browser acceptance test,
M0 evaluation, security audit, or self-assessed rubric score.

## Verified baseline

| Capability | Evidence and outcome | Remaining limitation |
| --- | --- | --- |
| Registration | Four existing registration tests pass: validation, duplicate rollback, password hashing, private fields, advising opt-in, and account preservation | No login, sessions, email verification, or profile ownership |
| Messaging | Three existing message tests pass: valid persistence, invalid input, missing and unavailable recipients | No recipient inbox, delivery notifications, or authenticated sender |
| Backend health | Temporary-database API smoke check returns `{"status":"ok"}` | No deployment verification |
| Course search | Fresh fictional seeds return Alex Morgan, Jordan Lee, and Sam Patel for CSC 510; unknown course returns no matches | Self-reported course completion |
| Profile creation/editing | Temporary-database API smoke check creates and edits a profile and reads it back after database reinitialization | Unauthenticated edits succeed; ownership protection is absent |
| Course data | API smoke check preserves completed/current courses and normalizes course codes | No university course verification |
| Advanced search | API smoke check combines course, program, year, skills, and advice topics; opt-out hides the profile unless `available=false` | No matching-quality evaluation or ranking evidence |
| Advice requests | Source inspection: request creation and accept/decline mutate React state | Lost on page reload; no backend request routes or recipient delivery |
| Supabase | Source inspection: environment-controlled client initialization exists | Routes still use SQLite; no live Supabase connection verified in this audit |
| Frontend | ESLint and production build pass | No browser interaction tests or automated frontend test script |

The extra API smoke checks were executed locally using Flask's test client and a
temporary SQLite database. They are not additional committed test cases and do
not increase the existing seven-test count. The user's runtime database was not
used or modified by these checks.

## Reproduce the existing automated checks

From the repository root, after installing dependencies as described in README:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -v
cd frontend
npm.cmd run lint
npm.cmd run build
cd ..
```

Observed: seven unittest methods pass, ESLint passes, Vite production build passes.
Registration/message tests include additional failure cases as subtests; these
are not represented here as additional standalone tests.

`npm.cmd` avoids the local PowerShell execution policy blocking `npm.ps1`.

## Browser acceptance checklist still to run

Start the backend/frontend using README. Use fictional information only.

- [ ] Register an account; confirm a useful duplicate-email error.
- [ ] Search CSC 510, inspect a profile, and try each additional filter.
- [ ] Create/edit a profile; reload and confirm saved fields persist.
- [ ] Cancel an edit and confirm it does not save.
- [ ] Save a message and confirm success/error feedback.
- [ ] Create and accept/decline an advice request, then reload and confirm the
      current limitation: it disappears and is not delivered to another user.
- [ ] Stop the backend and confirm connection-error feedback.

## Repository and rubric gaps

- `backend/peer_advice.db` is tracked, although `.gitignore` excludes new database
  files. Do not treat this as fictional-only data or publish its contents as
  audit evidence. See [the cleanup issue draft](issues/stop-tracking-runtime-database.md).
- `frontend/test_profile_editing.py` is empty and provides no test coverage.
- No tracked GitHub Actions workflow, coverage configuration/reporting, M0
  instrument, or frontend test runner was found.
- ESLint configuration exists. Shared formatting and Python lint configuration
  are missing.
- Required installation/contribution/license/conduct/dependency-inventory/AI-use
  documents and generated documentation were not found in the tracked files.
- Video, poster, DOI, discussion-channel, and self-assessment evidence have not
  been verified. GitHub repository visibility and remote issue/CI state could
  not be verified through the connected GitHub account.

## Step 1 follow-up

1. Post the database cleanup issue draft; discuss data/history handling before
   implementing it. Removing future tracking does not remove historical copies.
2. Have a teammate complete the browser acceptance checklist and record results.
3. In Step 2, agree on measurable milestones, especially M0 and authenticated
   profile ownership. Do not mark the frontend-only request flow or Supabase
   storage migration complete.

Audit and README corrections were prepared with Codex assistance. Automated
checks were executed by the agent; independent human review is still pending.
