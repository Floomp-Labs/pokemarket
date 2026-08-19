"""Vercel serverless entrypoint.

Vercel's Python runtime picks up the module-level `app` (any ASGI app).
The backend package lives one directory up from this file, so put the
project root on sys.path before importing it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402,F401
