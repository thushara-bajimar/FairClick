"""Start FairClick (API + simulated sites + built dashboard) on http://127.0.0.1:8000.

Usage:  python run.py            (after `npm run build` in frontend/ for the dashboard)
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

if __name__ == "__main__":
    import uvicorn

    from app.config import settings

    print(f"FairClick running at http://{settings.host}:{settings.port}  (Ctrl+C to stop)")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, log_level="info")
