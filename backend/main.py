"""Entry point for serverless hosts: Vercel looks for an `app` in main.py.

Docker and local runs use app.main:app directly (scripts/start.sh).
"""

from app.main import app  # noqa: F401
