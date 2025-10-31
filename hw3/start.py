# Tiny launcher so HW2 can run in containers without editing my app code.
# It imports hw2/app.py, discovers a Flask app object, and binds 0.0.0.0:5000.

import os
import sys
from importlib import import_module
from pathlib import Path

# Make hw2 importable
REPO_ROOT = Path(__file__).resolve().parents[1]
HW2_PATH = REPO_ROOT / "hw2"
sys.path.insert(0, str(HW2_PATH))

# Import module hw2/app.py as "app"
try:
    m = import_module("app")
except Exception as e:
    print("import error: could not import hw2/app.py as module 'app':", e, file=sys.stderr)
    sys.exit(2)

# Find a Flask app instance
flask_app = None

# Common case: module-level variable named "app"
if hasattr(m, "app"):
    flask_app = getattr(m, "app")

# Factory pattern fallback: create_app()
if flask_app is None and hasattr(m, "create_app"):
    try:
        flask_app = m.create_app()
    except Exception as e:
        print("create_app() failed:", e, file=sys.stderr)
        sys.exit(3)

# Last resort: scan globals for any Flask instance
if flask_app is None:
    try:
        from flask import Flask  # type: ignore
    except Exception as e:
        print("Flask import failed:", e, file=sys.stderr)
        sys.exit(4)
    for name, val in m.__dict__.items():
        if isinstance(val, Flask):
            flask_app = val
            break

if flask_app is None:
    print("no Flask app object found in hw2/app.py", file=sys.stderr)
    sys.exit(5)

# Bind to 0.0.0.0 for docker networking; default port 5000
port = int(os.environ.get("PORT", "5000"))
flask_app.run(host="0.0.0.0", port=port)
