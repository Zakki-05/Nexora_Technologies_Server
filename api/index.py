import os
import sys

# Add backend directory to sys.path so app modules are resolvable
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app

# Export app for Vercel Serverless WSGI/ASGI handler
handler = app
