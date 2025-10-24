# CS 530 HW2 - Songs MVP (Flask + sqlite3)

Minimal Flask app that supports creating and reading song entries.

- MVP pattern: routes + templates + model layer
- sqlite3 backend with an abstract model interface
- Runs on port 5000

## Run locally

Linux/macOS:
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
python app.py

Windows PowerShell:
python -m venv env
env\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py

Open http://127.0.0.1:5000

## Routes

- GET / Landing page with links
- GET /songs List all songs
- GET /songs/new Form to create a song
- POST /songs Create handler with basic validation

## Notes

- Title is required.
- Release month must be 1-12 when provided.
- Rating must be 0-10 when provided.
- Database file "songs.db" is created on first run.
