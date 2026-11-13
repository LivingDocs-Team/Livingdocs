"""Shared browser-test setup for the local Vite frontend."""

import os
import socket
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FRONTEND_URL = "http://127.0.0.1:3000/"
STARTUP_TIMEOUT_SECONDS = 60


def _port_is_open(host="127.0.0.1", port=3000):
    with socket.socket() as connection:
        connection.settimeout(0.25)
        return connection.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def start_frontend_for_browser_tests(request):
    """Build and start the repository's Vite preview for browser tests only."""
    if not any("page" in item.fixturenames for item in request.session.items):
        yield
        return

    if _port_is_open():
        if os.environ.get("FRONTEND_E2E_REQUIRED") == "true":
            try:
                with urllib.request.urlopen(FRONTEND_URL, timeout=5) as response:
                    if response.status != 200:
                        pytest.fail(f"Prestarted frontend returned HTTP {response.status}.")
            except (urllib.error.URLError, TimeoutError) as error:
                pytest.fail(f"Port 3000 is occupied but the prestarted frontend is unavailable: {error}")
            yield
            return
        pytest.fail(
            "Port 3000 is already in use. Stop the existing frontend server and "
            "rerun pytest, or set FRONTEND_E2E_REQUIRED=true when reusing the CI frontend."
        )

    log_file = tempfile.NamedTemporaryFile(prefix="livingdocs-vite-", suffix=".log", delete=False)
    log_path = Path(log_file.name)
    process = None
    try:
        build = subprocess.run(
            "npm.cmd run build",
            cwd=FRONTEND,
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if build.returncode != 0:
            pytest.fail(f"The frontend production build failed before browser tests. See {log_path}.")

        node = shutil.which("node")
        vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
        if not node or not vite.is_file():
            pytest.fail("Node.js and the installed frontend Vite dependency are required for browser tests.")
        process = subprocess.Popen(
            [node, str(vite), "preview", "--host", "127.0.0.1", "--port", "3000", "--strictPort"],
            cwd=FRONTEND,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        log_file.close()

        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(FRONTEND_URL, timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            pytest.fail(f"Vite did not become ready within {STARTUP_TIMEOUT_SECONDS}s. See {log_path}.")

        if process.poll() is not None:
            pytest.fail(f"Vite exited before becoming ready. See {log_path}.")

        yield
    finally:
        if not log_file.closed:
            log_file.close()
        if process is not None and process.poll() is None:
            # Vite runs in the process started above; terminate only that process.
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
