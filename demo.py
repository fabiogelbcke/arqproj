"""Run the portal against a fake Drive with sample data — no Google setup needed.

    python demo.py            # then open http://127.0.0.1:5000/casa-jardim
"""

import os
import tempfile
import threading

from werkzeug.serving import make_server

from tools.fake_drive import FakeDrive, service_account_json

FAKE_PORT = int(os.environ.get("FAKE_DRIVE_PORT", "8765"))
PORT = int(os.environ.get("PORT", "5000"))


def start_fake_drive() -> FakeDrive:
    if os.environ.get("LOCAL_TEST_PROJECTS"):
        from tools.folder_drive import FolderDrive
        fake = FolderDrive(f"http://127.0.0.1:{FAKE_PORT}", os.environ["LOCAL_TEST_PROJECTS"])
    else:
        fake = FakeDrive(f"http://127.0.0.1:{FAKE_PORT}")
    server = make_server("127.0.0.1", FAKE_PORT, fake.app(), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return fake


if __name__ == "__main__":
    fake = start_fake_drive()
    os.environ.update(
        GOOGLE_SERVICE_ACCOUNT_KEY=service_account_json(fake),
        DRIVE_API_BASE=f"http://127.0.0.1:{FAKE_PORT}/drive/v3",
        DRIVE_ROOT_FOLDER_ID=fake.root_id,
    )
    # The painel's "Connect Google Drive" goes to the fake consent page instead of
    # Google. Connection state and office settings start fresh on every launch, so
    # test mode never touches the files real Drive mode keeps in the project root.
    state_dir = tempfile.mkdtemp(prefix="arq-test-mode-")
    os.environ.update(
        OAUTH_CLIENT_ID="fake-client-id.apps.googleusercontent.com",
        OAUTH_CLIENT_SECRET="fake-client-secret",
        OAUTH_REDIRECT_URI=f"http://127.0.0.1:{PORT}/painel/drive/callback",
        OAUTH_AUTH_URI=f"http://127.0.0.1:{FAKE_PORT}/o/oauth2/v2/auth",
        OAUTH_TOKEN_URI=f"http://127.0.0.1:{FAKE_PORT}/token",
        PORTAL_STATE_FILE=os.path.join(state_dir, "drive-connection.json"),
        PORTAL_SETTINGS_FILE=os.path.join(state_dir, "portal-settings.json"),
    )
    for key in ("PORTAL_STATE_BUCKET", "SERVICE_ACCOUNT_EMAIL"):
        os.environ.pop(key, None)
    os.environ.setdefault("SITE_NAME", "ALINEA ARQUITETOS")
    os.environ.setdefault("SHOW_PROJECT_INDEX", "1")
    os.environ.setdefault("DASHBOARD_PASSWORD", "demo")

    from app import create_app

    print(f"\n  Demo running: http://127.0.0.1:{PORT}/casa-jardim")
    print(f"  Dashboard:    http://127.0.0.1:{PORT}/painel  (password: {os.environ['DASHBOARD_PASSWORD']})\n")
    create_app().run(host="127.0.0.1", port=PORT)
