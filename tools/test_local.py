"""Run Python and browser tests with isolated fake Drive data, without .env.

    .venv/bin/python -m tools.test_local

Install Python requirements, then `npm ci` and `npm run browsers:install` first.
Browser servers use available ports and are stopped even when a test fails.
"""

from contextlib import ExitStack, contextmanager
import argparse
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from unittest.mock import patch

from run_local import local_environment

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def serve(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def browser_tests(env):
    if not shutil.which("node") or not (ROOT / "node_modules/playwright").is_dir():
        print("Browser tests need Node.js and Playwright. Run npm ci, then npm run browsers:install.",
              file=sys.stderr)
        return 2

    from tools.fake_drive import FakeDrive, service_account_json

    fake = FakeDrive("http://127.0.0.1:0")
    # An in-progress standard project exercises completed, current and future
    # stages together. This only changes this run's in-memory fictional data.
    standard = next(n for n in fake.nodes.values() if n.name == "Projeto Padrão")
    config = next(n for n in standard.children if n.name == "_project")
    config.text = config.text.replace("Etapa atual: 1", "Etapa atual: 3")
    stage_two = next(n for n in standard.children if n.name.startswith("02 -"))
    fake._pdf("Levantamento de medidas.pdf", stage_two, 1)

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    with ExitStack() as stack:
        drive_url = stack.enter_context(serve(fake.app()))
        fake.base_url = drive_url
        env = dict(env, GOOGLE_SERVICE_ACCOUNT_KEY=service_account_json(fake),
                   DRIVE_API_BASE=f"{drive_url}/drive/v3", DRIVE_ROOT_FOLDER_ID=fake.root_id,
                   SITE_LANG="pt", SITE_NAME="Escritório de Teste", DASHBOARD_PASSWORD="demo",
                   SHOW_PROJECT_INDEX="1", CACHE_TTL_SECONDS="60")
        # The site's own address is part of its OAuth settings, so bind first and
        # build the app once the port is known.
        site = {}
        site_url = stack.enter_context(serve(lambda environ, start: site["app"](environ, start)))
        state_dir = stack.enter_context(TemporaryDirectory(prefix="arq-browser-"))
        env.update(OAUTH_CLIENT_ID="fake-client-id", OAUTH_CLIENT_SECRET="fake-secret",
                   OAUTH_REDIRECT_URI=f"{site_url}/painel/drive/callback",
                   OAUTH_AUTH_URI=f"{drive_url}/o/oauth2/v2/auth", OAUTH_TOKEN_URI=f"{drive_url}/token",
                   PORTAL_STATE_FILE=f"{state_dir}/drive-connection.json",
                   PORTAL_SETTINGS_FILE=f"{state_dir}/portal-settings.json")
        stack.enter_context(patch.dict(os.environ, env, clear=True))
        from app import create_app

        site["app"] = create_app()
        env.update(PROJECT_TEST_URL=f"{site_url}/casa-jardim",
                   STANDARD_PROJECT_TEST_URL=f"{site_url}/projeto-padrao",
                   PAINEL_TEST_URL=f"{site_url}/painel")
        for url in (env["PROJECT_TEST_URL"], env["STANDARD_PROJECT_TEST_URL"]):
            with urlopen(url, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError("Local fixture project did not start successfully.")
        print(f"Browser tests: isolated sample server at {site_url}", flush=True)
        files = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("*.test.cjs"))
        return subprocess.call(["node", "--test", *files], cwd=ROOT, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--python-only", action="store_true")
    group.add_argument("--browser-only", action="store_true")
    args = parser.parse_args()
    # Test mode never reads this path or inherits real Drive app settings.
    env = local_environment("test", ROOT / ".env")
    env["SITE_LANG"] = "pt"
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    codes = []
    if not args.browser_only:
        print("Python tests: isolated fake Drive and temporary folders", flush=True)
        codes.append(subprocess.call(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, env=env))
    if not args.python_only:
        codes.append(browser_tests(env))
    return 1 if any(codes) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
