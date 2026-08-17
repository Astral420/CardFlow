#!/usr/bin/env python3
"""
Development Environment Runner for CardFlow.

This script automates starting the complete local development stack:
1. Runs 'docker compose up -d postgres redis' in the repository root.
2. Runs Alembic database migrations ('upgrade head').
3. Starts the Uvicorn FastAPI backend server (http://localhost:8000).
4. Starts the Celery background worker (with --pool=solo on Windows, default pool on Linux/macOS).
5. Starts the Frontend Vite dev server ('npm run dev').

Usage:
    python scripts/dev.py
"""

import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def get_binaries():
    """Detect virtual environment python, celery, and npm binaries based on OS."""
    is_windows = platform.system() == "Windows"

    if is_windows:
        scripts_dir = BACKEND_DIR / ".venv" / "Scripts"
        python_bin = scripts_dir / "python.exe"
        celery_bin = scripts_dir / "celery.exe"
        npm_bin = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    else:
        scripts_dir = BACKEND_DIR / ".venv" / "bin"
        python_bin = scripts_dir / "python"
        celery_bin = scripts_dir / "celery"
        npm_bin = shutil.which("npm") or "npm"

    # Fallback to current sys.executable if .venv python is not found
    if not python_bin.exists():
        print(f"[!] Warning: Virtual environment python not found at {python_bin}. Falling back to {sys.executable}")
        python_bin = Path(sys.executable)

    return python_bin, celery_bin, npm_bin, is_windows


def step_docker_services():
    """Start PostgreSQL and Redis services via docker compose in root."""
    print("=" * 60)
    print("[1/3] Starting Docker services (PostgreSQL & Redis)...")
    print("=" * 60)
    cmd = ["docker", "compose", "up", "-d", "postgres", "redis"]
    print(f"Executing: {' '.join(cmd)} (cwd: {ROOT_DIR})")

    result = subprocess.run(cmd, cwd=ROOT_DIR)
    if result.returncode != 0:
        print(f"\n[!] Error: Failed to start docker containers (exit code {result.returncode}).", file=sys.stderr)
        print("[!] Ensure Docker Desktop / daemon is running.", file=sys.stderr)
        sys.exit(result.returncode)


def step_database_migrations(python_bin: Path):
    """Run Alembic migrations to bring database to 'head'."""
    print("\n" + "=" * 60)
    print("[2/3] Running Alembic database migrations (upgrade head)...")
    print("=" * 60)
    migration_code = "import os; os.chdir('backend'); from alembic.config import main; main(argv=['upgrade', 'head'])"
    cmd = [str(python_bin), "-c", migration_code]
    print(f"Executing: {' '.join(cmd)} (cwd: {ROOT_DIR})")

    result = subprocess.run(cmd, cwd=ROOT_DIR)
    if result.returncode != 0:
        print(f"\n[!] Error: Alembic migration failed (exit code {result.returncode}).", file=sys.stderr)
        sys.exit(result.returncode)


def step_run_services(python_bin: Path, celery_bin: Path, npm_bin: str, is_windows: bool):
    """Start Uvicorn server, Celery worker, and Frontend dev server concurrently."""
    print("\n" + "=" * 60)
    print("[3/3] Starting Backend API (Uvicorn), Background Worker (Celery), and Frontend (Vite)...")
    print("=" * 60)

    # Uvicorn command in backend/
    uvicorn_cmd = [str(python_bin), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"]

    # Celery command in backend/
    if celery_bin.exists():
        celery_cmd = [str(celery_bin), "-A", "app.celery_app", "worker", "--loglevel=info"]
    else:
        celery_cmd = [str(python_bin), "-m", "celery", "-A", "app.celery_app", "worker", "--loglevel=info"]

    if is_windows:
        print("[i] Detected Windows OS: adding '--pool=solo' to Celery worker.")
        celery_cmd.append("--pool=solo")
    else:
        print(f"[i] Detected {platform.system()} OS: using default Celery pool.")

    # Frontend command in frontend/
    frontend_cmd = [str(npm_bin), "run", "dev"]

    print(f"Starting Uvicorn:  {' '.join(uvicorn_cmd)}")
    print(f"Starting Celery:   {' '.join(celery_cmd)}")
    print(f"Starting Frontend: {' '.join(frontend_cmd)}")
    print("\nPress Ctrl+C to stop all services.\n")

    processes = []
    # Track Uvicorn separately so we can restart it on reload exits
    uvicorn_entry = None

    try:
        p_uvicorn = subprocess.Popen(uvicorn_cmd, cwd=BACKEND_DIR)
        uvicorn_entry = ["Uvicorn", p_uvicorn]
        processes.append(uvicorn_entry)

        p_celery = subprocess.Popen(celery_cmd, cwd=BACKEND_DIR)
        processes.append(["Celery", p_celery])

        p_frontend = subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR)
        processes.append(["Frontend", p_frontend])

        # Monitor processes
        while True:
            for entry in processes:
                name, proc = entry
                ret = proc.poll()
                if ret is None:
                    continue

                if name == "Uvicorn":
                    # Exit code 3 = Uvicorn triggered an internal reload; restart it.
                    # Any other exit code is a real crash — shut everything down.
                    if ret == 3:
                        print(f"[i] Uvicorn reloading (exit code 3). Restarting...")
                        new_proc = subprocess.Popen(uvicorn_cmd, cwd=BACKEND_DIR)
                        entry[1] = new_proc  # update in-place so finally sees it
                    else:
                        print(f"\n[!] Uvicorn crashed (exit code {ret}). Shutting down all services.")
                        return
                else:
                    print(f"\n[!] Process '{name}' exited unexpectedly (exit code {ret}). Shutting down all services.")
                    return

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n[i] KeyboardInterrupt received. Shutting down development services...")
    finally:
        for entry in processes:
            name, proc = entry
            if proc.poll() is None:
                print(f"[i] Terminating {name} (PID {proc.pid})...")
                proc.terminate()

        # Wait briefly for graceful shutdown, then kill if still running
        time.sleep(1)
        for entry in processes:
            name, proc = entry
            if proc.poll() is None:
                print(f"[!] Force killing {name} (PID {proc.pid})...")
                proc.kill()

        print("[✓] All development services stopped.")


def main():
    python_bin, celery_bin, npm_bin, is_windows = get_binaries()
    step_docker_services()
    step_database_migrations(python_bin)
    step_run_services(python_bin, celery_bin, npm_bin, is_windows)


if __name__ == "__main__":
    main()
