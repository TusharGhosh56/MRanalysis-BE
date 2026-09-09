import os
import sys

# Silence GitPython missing system git binary error on serverless runtimes
os.environ["GIT_PYTHON_REFRESH"] = "quiet"

# Ensure the project root directory is on sys.path for serverless runtimes
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.main import app  # noqa: E402




