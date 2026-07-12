# BuildScope Consultation Portal

A small Streamlit web application for collecting construction, architectural, and structural engineering consultation requirements.

This sample app is for requirement collection only. It does not generate final structural designs, calculations, engineering approvals, or construction recommendations. A licensed professional engineer or architect must review and approve all design and construction decisions based on local codes and regulations.

## Features

- Client/User role for project requirement submissions
- Save draft or submit final requirements
- File uploads for photos, sketches, plans, titles, and reference documents
- Map pin selection with latitude/longitude capture
- Submission status table
- Admin/Engineer role for filtering, reviewing, and updating projects
- Internal notes
- Uploaded file download
- PDF export for a project profile
- CSV export for filtered submissions

## Setup

```bash
python main.py
```

Then open:

```text
http://127.0.0.1:8000
```

No external Python packages are required. The map uses OpenStreetMap/Leaflet from a CDN in the browser, so the location picker works best with an internet connection.

## Default Storage

The app stores data locally in:

- `data/projects.json`
- `data/uploads/`

This keeps the sample simple for testing in Visual Studio Code. For production, replace local JSON storage with a proper database, authentication, access control, encrypted file storage, audit logs, validation, backups, and deployment hardening.

## Windows EXE

The packaged desktop-style app is:

```text
dist\BuildScopeApp.exe
```

Double-click `BuildScopeApp.exe` to start the app. It opens a local browser page:

```text
http://127.0.0.1:8000
```

Each computer runs its own local copy and stores its own data beside the `.exe` in a `data` folder. This is not a shared online database.

To rebuild the `.exe`, run:

```bat
BUILD_EXE.bat
```
