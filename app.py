"""
Hugging Face Spaces & Root Streamlit Entrypoint.
Delegates execution to src/ui/app.py.
"""

import os
import sys
import runpy

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

target_script = os.path.join(project_root, "src", "ui", "app.py")
runpy.run_path(target_script, run_name="__main__")
