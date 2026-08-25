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

import hashlib
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


@dataclass
class ServiceProcess:
    """A child service that can be restarted without disturbing its peers."""

    name: str
    command: list[str]
    cwd: Path
    process: subprocess.Popen | None = None

    def start(self) -> None:
        self.process = subprocess.Popen(self.command, cwd=self.cwd)

    def restart(self, grace_period: float = 1.0) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=grace_period)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self.start()


@dataclass
class PythonSourceWatcher:
    """Small dependency-free watcher used instead of Uvicorn reload on Windows."""

    root: Path
    snapshot: dict[Path, bytes] = field(init=False)

    def __post_init__(self) -> None:
        self.snapshot = self._take_snapshot()

    def _take_snapshot(self) -> dict[Path, bytes]:
        snapshot = {}
        for path in self.root.rglob("*.py"):
            try:
                snapshot[path] = hashlib.blake2b(
                    path.read_bytes(), digest_size=16
                ).digest()
            except FileNotFoundError:
                # Editors can replace a file between rglob() and read(). The
                # next polling pass will observe the replacement.
                continue
        return snapshot

    def changed(self) -> bool:
        latest = self._take_snapshot()
        changed = latest != self.snapshot
        self.snapshot = latest
        return changed


def uvicorn_command(python_bin: Path, is_windows: bool) -> list[str]:
    command = [str(python_bin), "-m", "uvicorn", "app.main:app", "--port", "8000"]
    if not is_windows:
        command.append("--reload")
    return command


def restart_exited_services(
    services: list[ServiceProcess], restart_delay: float = 0.5
) -> None:
    """Restart exited children individually while leaving healthy ones alone.

    Uvicorn and Vite normally reload inside their own supervisor processes,
    but that implementation detail and the resulting exit code vary between
    versions and platforms. An exited wrapper must therefore not be treated as
    a reason to tear down the entire development stack.
    """
    for service in services:
        process = service.process
        if process is None:
            continue

        return_code = process.poll()
        if return_code is None:
            continue

        print(
            f"\n[!] {service.name} exited (code {return_code}). "
            "Restarting that service..."
        )
        if restart_delay:
            time.sleep(restart_delay)
        service.start()


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

    # Uvicorn's Windows reloader broadcasts CTRL_C_EVENT to every process in
    # the terminal, including this supervisor. Watch backend sources here on
    # Windows instead; Uvicorn's native reloader remains enabled elsewhere.
    uvicorn_cmd = uvicorn_command(python_bin, is_windows)

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

    services = [
        ServiceProcess("Uvicorn", uvicorn_cmd, BACKEND_DIR),
        ServiceProcess("Celery", celery_cmd, BACKEND_DIR),
        ServiceProcess("Frontend", frontend_cmd, FRONTEND_DIR),
    ]
    backend_watcher = PythonSourceWatcher(BACKEND_DIR / "app") if is_windows else None

    try:
        for service in services:
            service.start()

        # Monitor processes
        while True:
            if backend_watcher is not None and backend_watcher.changed():
                print("\n[i] Backend source changed. Restarting Uvicorn...")
                services[0].restart()
            restart_exited_services(services)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n[i] KeyboardInterrupt received. Shutting down development services...")
    finally:
        for service in services:
            process = service.process
            if process is not None and process.poll() is None:
                print(f"[i] Terminating {service.name} (PID {process.pid})...")
                process.terminate()

        # Wait briefly for graceful shutdown, then kill if still running
        time.sleep(1)
        for service in services:
            process = service.process
            if process is not None and process.poll() is None:
                print(f"[!] Force killing {service.name} (PID {process.pid})...")
                process.kill()

        print("[✓] All development services stopped.")


def main():
    python_bin, celery_bin, npm_bin, is_windows = get_binaries()
    step_docker_services()
    step_database_migrations(python_bin)
    step_run_services(python_bin, celery_bin, npm_bin, is_windows)


if __name__ == "__main__":
    main()
