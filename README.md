# PackConnect — Peer Advice Portal

[![Build](https://github.com/kkattili_ncstate/PackConnect/actions/workflows/ci.yml/badge.svg?event=push)](https://github.com/kkattili_ncstate/PackConnect/actions/workflows/ci.yml)

PackConnect is a student-to-student peer-advice discovery portal being developed for NC State University. Students can search by course code to find peers who have completed a course and volunteered to share advice.

> **Project status:** Early working prototype. The application supports account registration. Login uses password verification and session cookies. Advice requests and accepted private chats use Supabase-backed storage. Course histories remain self-reported.

See the [Step 1 baseline audit](docs/STEP_1_AUDIT.md) for verified behavior, limitations, and outstanding work.

## Current features

- Register an account with email, password, and a student profile. Passwords are hashed; emails remain private. Advising is optional.
- Create and edit profiles with completed/current courses, skills, and advice topics. Only the signed-in owner can edit their profile; the API rejects unauthenticated or non-owner updates.
- Search by course code (for example, `CSC 510`) and filter by program, year, skills, advice topics, and advising availability.
- Display matching students who opted in to offer advice by default; the availability filter can include other profiles.
- Send persistent advice requests, view incoming/outgoing requests, and accept or decline as the recipient.
- View a student's profile, including program, year, bio, interests, and completed courses (as returned by the API).
- Use Supabase as the sole database, without automatically inserting fictional sample students.
- Get in-app bell notifications for incoming requests, request decisions, and new chat messages. Read/unread state is saved per account.
- Chat privately after acceptance. Both participants can send messages of up to 2,000 characters, and conversations persist across visits. Open chats refresh every three seconds.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React + Vite |
| Backend | Python + Flask + Flask-CORS |
| Database | Supabase (PostgreSQL) |
| Development environment | PyCharm or any code editor |

## Project structure

```text
PackConnect/
├── backend/
│   ├── app.py             # Flask API and Supabase integration

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

The backend connects to Supabase using the configuration in `backend/.env`. It does not create a local SQLite database or insert sample student records. Make sure your Supabase schema and environment variables are configured before starting. Leave this terminal running.

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

1. A fresh Supabase database should have no sample student profiles, so searches may initially return no results.
2. Register two student accounts and add completed-course information to their profiles.
3. Search for a course that a registered student has completed, then open that student's profile.
4. To test requests and chat, opt the recipient into advising. Sign in to the two accounts in separate browser profiles or a normal/incognito window. Send an advice request, accept it from the recipient's incoming requests, and then open chat.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/health` | Returns `{"status":"ok"}` |
| POST | `/api/auth/register` | Creates an account and student profile; returns 201, 400 for invalid input, or 409 for a duplicate email |
| GET | `/api/students/search?course=CSC%20510` | Finds opted-in students who completed the specified course |
| GET | `/api/students/1` | Retrieves a student's full profile |
| GET / POST | `/api/requests` | List your requests or create one for another registered advisor |
| PATCH | `/api/requests/1` | Recipient accepts/declines a pending request |
| GET / POST | `/api/requests/1/messages` | Read/send messages after acceptance; participants only |

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
- Supabase is the sole database. The application does not create or use a local SQLite database, and existing SQLite data is not migrated.
- Supabase should start without fictional sample profiles or messages.
- Requests and chat use the signed-in account identity. Only the two participants can read requests/conversations, and only the recipient can accept or decline. Email/push notifications are not implemented.
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
- Message read receipts, notifications, and conversation management.
- Improved testing, validation, privacy, and deployment configuration.

---

**Repository:** https://github.com/kkattili_ncstate/PackConnect

### Supabase setup for collaborators

Supabase is the application's only database. Each developer needs a local `backend/.env` file with these settings:

```dotenv
SUPABASE_URL=your_project_url
SUPABASE_SECRET_KEY=your_server_secret_key
SUPABASE_PUBLISHABLE_KEY=your_publishable_key
```

Get these values from the authorized Supabase project settings. Keep `.env` private and never commit it. Do not expose the secret key in frontend code.

Install backend dependencies with `python -m pip install -r backend/requirements.txt` and configure the required Supabase schema before running the backend.

The application does not seed fictional profiles or messages. Existing SQLite data is not migrated. If you need an old local database, preserve it privately and do not commit it. Removing a database from the current version does not remove copies from Git history; the team should assess historical cleanup separately.
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
Profile updates require the signed-in owner. Standalone profile creation still
needs additional permissions. Chat and advice requests require authentication
and participant access. Password reset, email verification, and login rate
limiting are not implemented in this change.

### Workspace pages

- `#/app`: Find peers with course search, collapsible advanced filters, and removable filter chips.
- `#/app/students/<id>`: A dedicated student profile, including an advice request form for registered advisors and chat links for existing connections.
- `#/app/profile`: Your own profile, with an Edit Profile button.
- `#/app/profile/edit`: Edit your own profile; Save persists changes and Cancel discards edits.
- `#/app/requests`: Persistent Incoming and Outgoing requests, recipient accept/decline controls, and accepted conversation links.

Shared navigation includes a mobile menu. Profile links support refresh and
browser Back/Forward. Profiles are created during registration; the search page
no longer offers duplicate profile creation. `PUT /api/students/<id>` returns
401 without a session, 403 for another user's profile, and 400 for invalid input.
Permission failures do not modify profile or course records.

### Persistent requests and private chat

Restart Flask after updating to create the new tables automatically. Existing
profiles, accounts, and legacy messages are retained. Old unauthenticated
messages are not imported into private conversations because they lack verified
sender identities. The previous `/api/students/<id>/messages` endpoint now
returns 410; clients must use accepted-request conversations.

`#/app/chat/<request-id>` opens a conversation. Only its sender and recipient can
read or send messages, and only after acceptance. One pending/accepted connection
is allowed per student pair, including requests in the opposite direction.
Declined requests stay in history, and a new request may be sent. Accepted or
declined decisions cannot be reversed through the API. Turning off future advice
availability does not delete existing connections or messages.

The Requests list refreshes on navigation and every eight seconds. Open chats
poll every three seconds and fetch history in batches of 100. Requests/messages
survive reloads and backend restarts; sign in again if a development restart
invalidates your session. See [messaging API and test instructions](docs/MESSAGING.md).

### Notifications

The header bell shows unread updates for new connection requests, accepted or
declined requests, and new chat messages. Open it to inspect updates. Selecting
an update marks it read and opens the relevant inbox, outgoing request, or chat.
**Mark all as read** clears the unread state for updates up to the latest loaded
notification, preserving newer arrivals. Read state persists across visits.

Notifications refresh every five seconds while the app is open. No browser
permission is needed; these are in-app alerts, not email or operating-system
push notifications. Restart Flask after updating to create notification storage.
Existing pending requests and completed decisions are backfilled once without
resetting previously read updates. The panel shows the latest 50 events; the
badge counts all unread events. Chat message content is not included in the
notification preview. All notification APIs are scoped to the signed-in account.
