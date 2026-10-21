# Profile and advanced-search test evidence

This records automated backend coverage for the acceptance checklist in issue #9,
including the profile validation fix exposed by the new regression tests.

## Acceptance checklist

| Issue criterion | Evidence |
| --- | --- |
| Profile creation, editing, and persisted courses | Registration creates the profile; GET verifies persisted fields/courses; owner-update tests verify scalar fields and both course lists |
| Required fields and malformed payloads without server errors | Missing/blank required fields, malformed JSON, wrong content types, non-object JSON, incorrect field types, booleans, and malformed course arrays return 400 |
| Missing profile IDs | Missing GET and stale-session PUT after profile deletion return 404 |
| Course normalization and each filter | Dedicated normalization and course/program/year/skills/advice-topic tests |
| Combined filters, empty results, advising availability | Near-match fixtures, contradictory/empty queries, and availability/toggle tests |
| Rejected writes leave data unchanged | Rejected edits compare exact stored profile and course rows, including course row IDs; invalid registration and duplicate-email rollback tests verify storage counts |
| Isolated temporary databases | A dedicated localhost PostgreSQL test database gives each test a unique temporary schema; cleanup drops the schema; the helper rejects non-local test URLs |
| Replace/remove empty placeholder | Removed the empty `frontend/test_profile_editing.py`; executable API tests live under `backend/` and are discovered by CI |

## Coverage

| Behavior | Automated evidence |
| --- | --- |
| Program, year, skills, and advice topics independently | Four dedicated tests in `backend/test_search.py`, including mixed case, trimmed input, and partial text matches |
| All filters combined | Near-matching fictional profiles ensure every filter is applied; contradictory combinations return no matches |
| Completed-course search | Case/outer-whitespace normalization; a current course alone cannot satisfy completed-course search |
| Advising availability | Default and explicit true exclude opted-out profiles; `available=false` includes both availability states |
| Empty and unknown searches | No filters, whitespace, availability alone, and unknown values return empty arrays |
| Stable public results | Sorted results with exact expected IDs, no duplicate students from repeated course records, and only public summary fields |
| SQL-shaped search input | Quoted SQL text is treated as a search value and cannot bypass filters |
| Profile field persistence | Owner edits are read back with every editable scalar field and both course lists verified |
| Course replacement and clearing | Case/whitespace normalization, deduplication, repeated saves, removal of old courses, and empty lists/optional fields |
| Search reflects profile changes | Replacing courses removes old matches and adds new ones; toggling advising changes visibility |
| Missing profiles | GET returns 404; editing a deleted profile with an existing session returns 404 without recreating course records |
| Existing permissions and validation | Existing profile tests continue to cover 401/403, invalid updates, and unchanged profile/course data after rejection |

The changes add 14 search test methods, nine profile test methods, and two
registration test methods, and expand existing owner-update/registration
assertions. Subtests are not counted as separate tests.

The malformed-field regression test initially reproduced successful writes for
invalid values (such as a numeric name, string availability, or a non-list course
field). Profile validation now rejects these with 400 before opening a write
transaction. Text fields require strings, availability requires a boolean, and
courses require arrays of strings. Valid course codes still normalize and
deduplicate, with blank entries ignored as before.

## Reproduce

Use a dedicated localhost PostgreSQL instance with schema/role creation
privileges. The test helper gives every test a new schema and removes it during
cleanup. Live Supabase data is not used. See [database test setup](SUPABASE.md).

```sh
TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/packconnect_test?sslmode=disable' \
  .venv/bin/python -m unittest discover -s backend -p 'test_*.py' -v
```

## Observed result

On October 21, 2026, the complete backend suite ran on isolated PostgreSQL 17:

```text
Ran 79 tests in 10.407s
OK (skipped=2)
```

That is 77 passing test methods, including all 25 newly added methods. The two
live Supabase integration tests were intentionally skipped because their opt-in
flag was not set. The run includes the profile validation fix and placeholder
removal. Subsequent registration read-back assertions are verified separately.
The focused registration test passed (one test in 0.123s).

The existing GitHub Actions backend job discovers these files automatically.
The result above is local evidence; a hosted CI run for the new changes still
requires committing and pushing them. This work does not measure coverage
percentages or add browser interaction tests (issues #11 and #10).
