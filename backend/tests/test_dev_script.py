from pathlib import Path

from scripts import dev


class FakeProcess:
    def __init__(self, return_code=None, pid=1):
        self.return_code = return_code
        self.pid = pid
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.return_code

    def terminate(self):
        self.terminated = True
        self.return_code = 0

    def wait(self, timeout=None):
        return self.return_code

    def kill(self):
        self.killed = True
        self.return_code = -1


def _service(name: str, process: FakeProcess) -> dev.ServiceProcess:
    return dev.ServiceProcess(name, [name.lower()], Path("."), process)


def test_frontend_exit_restarts_only_frontend(monkeypatch):
    uvicorn = _service("Uvicorn", FakeProcess())
    celery = _service("Celery", FakeProcess())
    frontend = _service("Frontend", FakeProcess(return_code=0))
    replacement = FakeProcess(pid=4)
    starts = []

    def fake_popen(command, cwd):
        starts.append((command, cwd))
        return replacement

    monkeypatch.setattr(dev.subprocess, "Popen", fake_popen)

    dev.restart_exited_services([uvicorn, celery, frontend], restart_delay=0)

    assert uvicorn.process.pid == 1
    assert celery.process.pid == 1
    assert frontend.process is replacement
    assert starts == [(["frontend"], Path("."))]


def test_backend_exit_code_is_not_assumed_to_be_a_fatal_crash(monkeypatch):
    uvicorn = _service("Uvicorn", FakeProcess(return_code=1))
    frontend = _service("Frontend", FakeProcess())
    replacement = FakeProcess(pid=3)

    monkeypatch.setattr(dev.subprocess, "Popen", lambda command, cwd: replacement)

    dev.restart_exited_services([uvicorn, frontend], restart_delay=0)

    assert uvicorn.process is replacement
    assert frontend.process.pid == 1


def test_windows_uvicorn_does_not_use_ctrl_c_broadcasting_reloader():
    command = dev.uvicorn_command(Path("python.exe"), is_windows=True)

    assert "--reload" not in command
    assert command[-2:] == ["--port", "8000"]


def test_non_windows_uvicorn_keeps_native_reloader():
    command = dev.uvicorn_command(Path("python"), is_windows=False)

    assert command[-1] == "--reload"


def test_windows_source_watcher_detects_backend_change(tmp_path):
    source = tmp_path / "route.py"
    source.write_text("VERSION = 1\n", encoding="utf-8")
    watcher = dev.PythonSourceWatcher(tmp_path)

    assert watcher.changed() is False

    source.write_text("VERSION = 200\n", encoding="utf-8")

    assert watcher.changed() is True
    assert watcher.changed() is False


def test_source_reload_replaces_only_the_managed_service(monkeypatch):
    old_uvicorn = FakeProcess()
    uvicorn = _service("Uvicorn", old_uvicorn)
    replacement = FakeProcess(pid=2)
    monkeypatch.setattr(dev.subprocess, "Popen", lambda command, cwd: replacement)

    uvicorn.restart(grace_period=0)

    assert old_uvicorn.terminated is True
    assert uvicorn.process is replacement
