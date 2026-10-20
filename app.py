"""
Streamlit & Cloud Entrypoint.
Initializes data layer and delegates execution to src/ui/app.py.
"""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Explicitly ensure database tables and synthetic data are loaded
try:
    from src.database import db
    db.ensure_loaded()
except Exception as e:
    print(f"Startup database initialization error: {e}")

import runpy
target_script = os.path.join(project_root, "src", "ui", "app.py")
runpy.run_path(target_script, run_name="__main__")
