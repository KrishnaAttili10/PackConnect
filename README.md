# PackConnect — Peer Advice Portal

PackConnect is a student-to-student peer-advice discovery portal being developed for NC State University. Students can search by course code to find peers who have completed a course and volunteered to share advice.

> **Project status:** Early working prototype. The current application uses fictional student data for development and demonstration. Messages can be saved locally; user accounts, student inboxes, and verified course histories are not implemented yet.

## Current features

- Search for students by an exact course code (for example, `CSC 510`).
- Display matching students who opted in to offer advice.
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
│   └── peer_advice.db     # Created locally; not committed
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
python -m pip install flask flask-cors
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

> **PowerShell note:** If script execution is blocked when activating the virtual environment, you can skip activation and run `.\.venv\Scripts\python.exe -m pip install flask flask-cors` followed by `.\.venv\Scripts\python.exe backend/app.py`.

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
| GET | `/api/students/search?course=CSC%20510` | Finds opted-in students who completed the specified course |
| GET | `/api/students/1` | Retrieves a student's full profile |
| POST | `/api/students/1/messages` | Saves a message; JSON body: `{"sender_name":"Casey","body":"Any study tips?"}` |

Quick browser checks:

- [Backend health](http://127.0.0.1:5000/api/health)
- [CSC 510 search](http://127.0.0.1:5000/api/students/search?course=CSC%20510)
- [Frontend](http://localhost:5173/)

## Development notes

- The frontend currently calls `http://127.0.0.1:5000` directly. Run Flask on port **5000** unless you also update `API_URL` in `frontend/src/App.jsx`.
- Vite usually runs on port **5173**. If that port is busy, use the URL printed by `npm run dev`.
- Flask runs in **debug mode** for local development. Do not deploy the development server to production.
- SQLite data is local and is **not pushed to GitHub**. Each developer gets their own seeded database.
- The example students are fictional; no real student information is required for the prototype.
- Messaging currently saves messages locally with a self-reported sender name. Authentication, inboxes, and notifications are planned features.
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

- Student signup/login and profile editing.
- Course completion reporting and richer course discovery.
- Connection requests and student-to-student messaging.
- Improved testing, validation, privacy, and deployment configuration.

---

**Repository:** https://github.com/kkattili_ncstate/PackConnect
