# Stop tracking the runtime SQLite database and use fictional seed data

Status: issue draft; not posted to GitHub. The connected GitHub account could
not search/access `kkattili_ncstate/PackConnect` during the Step 1 audit.

## Problem

`git ls-files '*.db'` lists `backend/peer_advice.db`. Existing `.gitignore` rules
do not untrack files already committed. The database can contain locally entered
account/profile/message records and does not match the documented local-only
storage model.

Do not copy database contents into this issue or attach a runtime database.

## Expected behavior

Fresh clones create a local database from fictional seeds. Existing developers
retain any local data they need without committing it.

## Acceptance criteria

- [ ] Each developer backs up any needed local database before pulling a removal.
- [ ] Remove the runtime database from Git tracking while retaining a local copy
      for the person making the change (`git rm --cached backend/peer_advice.db`).
- [ ] Confirm `git ls-files '*.db'` returns no runtime database files.
- [ ] Confirm a freshly generated database contains fictional seed students and
      no pre-existing accounts/messages.
- [ ] Existing registration and messaging tests pass using temporary databases.
- [ ] Document fresh-clone initialization and existing-clone backup precautions.
- [ ] Discuss whether historical data requires removal; do not rewrite shared
      history without an agreed team plan. Future untracking alone is not history cleanup.

## Verification

Use a disposable clone or temporary database to verify initialization. Do not
delete a developer's runtime data as a test. Run:

```powershell
git ls-files '*.db'
.\.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -v
```

## Discussion required before closing

Record backup coordination, history-handling decisions, the implementation PR,
and test evidence. No cleanup or history rewrite was performed during Step 1.

## Implementation update

The fix branch removes the database from tracking while retaining the local
runtime file. An integrity-checked SQLite backup was created under the ignored
`.local-backups/` directory. A fresh-database regression test verifies the four
fictional seed students, empty account/message/current-course tables, and course
search. README now documents backups for existing clones and initialization for
fresh clones.

Pending before merge/closure: teammates confirm their backups, link the PR to
the actual GitHub issue, and record the team's historical-data decision. No
history rewrite or teammate backup confirmation has been performed by the agent.
