# Palm Route Air – Web Operations Console

This is a small local Flask web app that gives you **click-and-fill forms with persistence** for Palm Route Air (PRA):

- Cargo Manifests
- Dispatch Releases
- Crew / Pilot Flight Logs
- Company NOTAMs
- Fleet Management

All data is stored in a local **SQLite** database file (`palm_route_air.db`) inside the `webapp/` folder.

## Prerequisites

- Python 3.10+ installed and available on your PATH

## Setup (Windows PowerShell)

From the project root (`palm_route_air`):

```powershell
cd .\webapp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the app

With the virtual environment activated and in the `webapp` folder:

```powershell
python .\app.py
```

By default Flask will start on `http://127.0.0.1:5000/`.

Open that in your browser and use the navigation bar to access each PRA form. Each submission is saved to the SQLite database and can be viewed via the corresponding **History** page.

## Notes

- The database schema is created automatically the first time the app receives a request.
- This app is intended for **local use only** (virtual airline gameplay support), not for public internet exposure.
