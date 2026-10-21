# PackConnect — Peer Advice Portal

[![Build](https://github.com/kkattili_ncstate/PackConnect/actions/workflows/ci.yml/badge.svg?event=push)](https://github.com/kkattili_ncstate/PackConnect/actions/workflows/ci.yml)

PackConnect is a student-to-student peer-advice discovery portal being developed for NC State University. Students can search by course code to find peers who have completed a course and volunteered to share advice.

> **Project status:** Early working prototype. The application includes fictional sample students and account registration. Messages can be saved locally; login uses password verification and session cookies; student inboxes and verified course histories are not implemented yet.

See the [Step 1 baseline audit](docs/STEP_1_AUDIT.md) for verified behavior, limitations, and outstanding work.

## Current features

- Register an account with email, password, and a student profile. Passwords are hashed; emails remain private. Advising is optional.
- Create and edit profiles with completed/current courses, skills, and advice topics. Only the signed-in owner can edit their profile; the API rejects unauthenticated or non-owner updates.
- Search by course code (for example, `CSC 510`) and filter by program, year, skills, advice topics, and advising availability.
- Display matching students who opted in to offer advice by default; the availability filter can include other profiles.
- Create and accept/decline advice requests within the current browser session. Requests are not delivered or saved and disappear on reload.
- View a student's profile, including program, year, bio, interests, and completed courses (as returned by the API).
- Automatically seed a local SQLite database with sample students on first backend startup.
- Send an advice message from a student's profile using your name and a message of up to 2,000 characters. Messages are saved in SQLite; there is no inbox or notification delivery yet.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React + Vite |
| Backend | Python + Flask + Flask-CORS |
| Database | SQLite |
| Development environment | PyCharm or any code editor |

## Project structure

```text
PackConnect/
├── backend/
│   ├── app.py             # Flask API and database initialization
│   └── peer_advice.db     # Created locally from fictional seeds; not tracked
├── frontend/
│   ├── src/
│   │   ├── App.jsx        # Search and student profile UI
│   │   ├── App.css
│   │   └── index.css
│   ├── package.json
│   └── package-lock.json
├── .gitignore
└── README.md
```

## Prerequisites

Install:

- **Python 3.11 or later** (use a version supported by the project's Flask dependencies).
- **Node.js 24 LTS** (recommended for the current Vite/Rolldown setup) and npm.
- **Git** to clone the repository.

You do **not** need Visual Studio or Visual Studio Build Tools to run this prototype. PyCharm is optional.

Check your installed versions:

```powershell
python --version
node -v
npm -v
git --version
```

## Run locally (Windows / PowerShell)

### 1. Clone the repository

```powershell
git clone https://github.com/kkattili_ncstate/PackConnect.git
cd PackConnect
```

If you've already cloned it, open a terminal in the existing project folder instead.

### 2. Start the Flask backend

From the **repository root**, create and activate a Python virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install backend dependencies:

```powershell
python -m pip install -r backend/requirements.txt
```

Start Flask:

```powershell
python backend/app.py
```

The backend should report:

```text
Running on http://127.0.0.1:5000
```

On first startup, it creates `backend/peer_advice.db` and inserts fictional sample student records. Leave this terminal running.

> **PowerShell note:** If script execution is blocked when activating the virtual environment, you can skip activation and run `.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt` followed by `.\.venv\Scripts\python.exe backend/app.py`.

### 3. Start the React frontend

Open a **second terminal** in the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

`npm ci` installs dependencies from `package-lock.json`. If the lockfile is missing, use `npm install` instead.

Vite should print a local URL, usually:

```text
http://localhost:5173/
```

Open that URL in your browser. **The frontend is the actual website; port 5000 serves only the API.**

### 4. Try the application

1. Search for `CSC 510`.
2. The seeded database should return **Alex Morgan, Jordan Lee, and Sam Patel**.
3. Click **View Profile** to see a student's details.
4. Try `CSC 540` or `CSC 515` for other matches.
5. Open a profile, enter your name and message, and click **Send Message**. Restart the backend after updating so it creates the messages table in your existing database.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Returns `{"status":"ok"}` |
| POST | `/api/auth/register` | Creates an account and student profile; returns 201, 400 for invalid input, or 409 for a duplicate email |
| GET | `/api/students/search?course=CSC%20510` | Finds opted-in students who completed the specified course |
| GET | `/api/students/1` | Retrieves a student's full profile |
| POST | `/api/students/1/messages` | Saves a message; JSON body: `{"sender_name":"Casey","body":"Any study tips?"}` |

Quick browser checks:

- [Backend health](http://127.0.0.1:5000/api/health)
- [CSC 510 search](http://127.0.0.1:5000/api/students/search?course=CSC%20510)
- [Frontend](http://localhost:5173/)

### Account registration

Restart the backend after updating to create the accounts table in your existing database. Click **Create account** in the frontend header. Enter your name, email, a password of 12–128 characters, program, and year. Optional fields include bio, interests, and comma-separated completed courses. Opt in to advising to appear in searches for those courses.

The registration API accepts `name`, `email`, `password`, `program`, and `year`, plus optional `bio`, `interests`, `completed_courses` (an array of course codes), and `willing_to_advise` (a boolean, defaulting to false). Email uniqueness ignores case. Account and profile creation are transactional. After registration, sign in on the login page. Email verification is not yet implemented. Course completion is self-reported.

## Development notes

- The frontend uses same-origin `/api` requests. Vite proxies them to `http://127.0.0.1:5000`; restart Vite after updating its configuration. Production hosting must proxy `/api` to Flask as well.
- Vite usually runs on port **5173**. If that port is busy, use the URL printed by `npm run dev`.
- Flask runs in **debug mode** for local development. Do not deploy the development server to production.
- SQLite is the active storage backend. Runtime databases are ignored and are no longer tracked in this version. Existing clones must follow the backup instructions below before pulling the removal. Historical commits still contain the old database.
- The example students are fictional; no real student information is required for the prototype.
- Messaging currently saves messages locally with a self-reported sender name. Login, inboxes, and notifications are planned features.
- Run backend messaging checks with `python -m unittest discover -s backend -p "test_*.py"` and frontend checks with `npm run build` and `npm run lint` from `frontend`.

## Common troubleshooting

**`python: can't open file 'backend/app.py'`**  
Make sure you're in the repository root (`PackConnect`) when running `python backend/app.py`.

**The frontend says it cannot connect to Flask**  
Start the backend in a separate terminal and check [the health endpoint](http://127.0.0.1:5000/api/health).

**`Cannot find native binding` (Rolldown)**  
Use a supported Node.js version (Node 24 LTS recommended), then from the `frontend` folder run:

```powershell
Remove-Item -Recurse -Force .\node_modules
npm ci --include=optional
npm run dev
```

If `npm ci` cannot run because the lockfile is missing, use `npm install --include=optional`.

**PowerShell says `Activate.ps1` cannot be loaded**  
Use the direct virtual-environment Python commands in the backend setup section instead.

## Working with Git

Before starting work, pull the latest changes:

```powershell
git pull origin main
```

Create a feature branch for your changes:

```powershell
git switch -c feature/short-description
```

After making changes:

```powershell
git add .
git commit -m "Describe your change"
git push -u origin feature/short-description
```

Open a pull request on GitHub for team review before merging into `main`.

## Planned improvements

- Authenticated permissions for the remaining profile-creation and messaging endpoints.
- Course completion reporting and richer course discovery.
- Persistent advice requests, recipient inboxes, and authenticated messaging.
- Improved testing, validation, privacy, and deployment configuration.

---

**Repository:** https://github.com/kkattili_ncstate/PackConnect

### Supabase connection setup

Install backend dependencies with `python -m pip install -r backend/requirements.txt`.
To initialize the optional Supabase client, create `backend/.env` with
`SUPABASE_URL` and `SUPABASE_SECRET_KEY` from your Supabase project. Keep this file
local; it is ignored by Git. Both values must be set together. With neither set,
the application runs locally without a Supabase client.

The client is available as `supabase` in `backend/app.py`. API routes currently
store data in SQLite; this connection setup does not migrate data or switch
those routes to Supabase.

### Existing clones: back up before pulling the database removal

Stop the Flask backend before making a file backup. From the repository root:

```powershell
$databaseBackupDir = Join-Path $env:TEMP ("PackConnect-db-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $databaseBackupDir | Out-Null
Copy-Item -LiteralPath backend/peer_advice.db -Destination (Join-Path $databaseBackupDir "peer_advice.db")
Write-Output "Database backup: $databaseBackupDir"
```

Keep the printed backup path. Pulling or switching to a commit that removes the
tracked database can delete that file from an existing checkout. After updating,
restore the backup to `backend/peer_advice.db` if you want your previous local data.
Do not add the restored file to Git.

For a fresh clone, no database download is needed. Running
`.\.venv\Scripts\python.exe backend/app.py` creates the SQLite database and four
fictional student profiles. It creates no accounts or messages. Run
`git ls-files '*.db'` to confirm no database is tracked, and
`git check-ignore backend/peer_advice.db` to confirm the ignore rule applies.

This change stops future database tracking; it does not remove historical
copies. The team must record its decision about historical data in the cleanup
issue before closing it. Shared Git history has not been rewritten.

### Automated checks

GitHub Actions runs backend tests, frontend ESLint, and the frontend production
build on every push and pull request. No private credentials are required. See
[CI instructions](docs/CONTINUOUS_INTEGRATION.md) for local commands and how to
inspect a run. The build badge links to the live workflow evidence.

### Login and public pages

Open the Vite URL to reach the login landing page. Create an account, then sign
in with its email and password to open `#/app`. Existing fictional seed students
have no login accounts. About, Privacy policy, and Terms & conditions are
available without signing in. These informational policy pages describe the
prototype and should be reviewed by the project team before public deployment.

Sessions use an HttpOnly, SameSite=Lax cookie and expire after eight hours.
Refresh restores a valid session; Sign out clears it. For stable sessions across
backend restarts, set `FLASK_SECRET_KEY` to a strong private value in `backend/.env`.
Without it, development uses a fresh random key per process. Use HTTPS and set
`COOKIE_SECURE=true` when deploying. The login gate controls frontend navigation;
profile updates require the signed-in owner. Standalone profile creation and
message endpoints still need additional permissions. Password reset, email verification, and login rate limiting are not
implemented in this change.

### Workspace pages

- `#/app`: Find peers with course search, collapsible advanced filters, and removable filter chips.
- `#/app/students/<id>`: A dedicated student profile, including advice/message forms when available.
- `#/app/profile`: Your own profile, with an Edit Profile button.
- `#/app/profile/edit`: Edit your own profile; Save persists changes and Cancel discards edits.
- `#/app/requests`: Session-only request preview, not a persistent recipient inbox.

Shared navigation includes a mobile menu. Profile links support refresh and
browser Back/Forward. Profiles are created during registration; the search page
no longer offers duplicate profile creation. `PUT /api/students/<id>` returns
401 without a session, 403 for another user's profile, and 400 for invalid input.
Permission failures do not modify profile or course records.
