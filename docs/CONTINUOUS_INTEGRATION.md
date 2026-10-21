# Continuous integration

The `Build` workflow in `.github/workflows/ci.yml` runs for every branch push
and pull request. It can also be started manually from the GitHub Actions page
once the workflow exists on the default branch.

## Checks

| Job | Environment | Commands |
| --- | --- | --- |
| Backend tests | Ubuntu, Python 3.12 | Install `backend/requirements.txt`; run unittest discovery |
| Frontend lint and build | Ubuntu, Node.js 24 | Run `npm ci`, `npm run lint`, and `npm run build` in `frontend` |

Each job has a ten-minute timeout. Installation, test, lint, or build failures
fail the corresponding job and workflow; failures are not suppressed.

The backend tests run in temporary schemas on a PostgreSQL 17 service. CI sets
`TEST_DATABASE_URL` to that local service and keeps live Supabase settings empty.
No live Supabase credentials or GitHub repository secrets are required. The
schema fixtures supply the minimal Supabase roles and Auth reference table.
Live integration tests are skipped unless explicitly enabled.

Dependency download caches are keyed by the backend requirements or frontend
lockfile; frontend packages are installed with `npm ci` from the lockfile.

## Local verification

From the repository root after installing dependencies and setting
`TEST_DATABASE_URL` to a dedicated localhost PostgreSQL database (see
[database verification](SUPABASE.md)):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -v
cd frontend
npm.cmd ci
npm.cmd run lint
npm.cmd run build
cd ..
```

CI uses `npm` on Ubuntu; `npm.cmd` is the Windows equivalent that avoids
PowerShell script-execution restrictions. Local runtime versions may differ
from CI; the hosted workflow is the evidence for Python 3.12 and Node.js 24.

## Review the evidence

1. Push a commit or open a pull request.
2. Open the repository's **Actions** tab and select **Build**.
3. Select the run for the exact branch and commit you are reviewing.
4. Confirm both jobs succeed and inspect their installation/check logs.
5. If a job fails, fix the cause and push another commit. Preserve the failed
   run as evidence rather than describing it as a successful check.

The README badge links to this workflow and displays the latest push result.
After this workflow is merged to `main`, the badge can be scoped to `main` with
`?branch=main&event=push` for an explicit default-branch status.

This issue adds test execution, lint, and build automation. It does not add
coverage, a numerical test badge, frontend interaction tests, or branch
protection. Those are separate tasks. CI checks can fail a PR, but preventing
merges of failing PRs requires repository branch rules.
