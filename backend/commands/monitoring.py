"""Email alerts for the live site (plan section 21).

    uv run python -m backend.commands.monitoring --email you@example.com

Makes Google Cloud match `deploy/production/monitoring/`: the log-based metric
(`*.metric.json`), an email channel for the address, and the alert policies
(`*.policy.json`) sending to it. Each is found by its name and updated in place,
so a re-run after editing a file changes it rather than adding a second one.

Signs in as you (`gcloud auth application-default login`, once): your account
needs to edit monitoring and logging in the project.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

MONITORING = "https://monitoring.googleapis.com/v3"
LOGGING = "https://logging.googleapis.com/v2"
FILES = Path(__file__).resolve().parents[2] / "deploy" / "production" / "monitoring"
PROJECT = "arq-proj"

# method, url, query, body -> (status, body)
Call = Callable[[str, str, dict | None, dict | None], tuple[int, dict]]


def _ok(answer: tuple[int, dict], doing: str) -> dict:
    status, body = answer
    if status >= 300:
        raise SystemExit(f"{doing} failed ({status}): {body.get('error', {}).get('message', body)}")
    return body


def _metric(call: Call, project: str, metric: dict) -> str:
    url = f"{LOGGING}/projects/{project}/metrics"
    status, _ = call("GET", f"{url}/{metric['name']}", None, None)
    if status == 404:
        _ok(call("POST", url, None, metric), f"creating metric {metric['name']}")
        return f"created metric {metric['name']}"
    _ok(call("PUT", f"{url}/{metric['name']}", None, metric), f"updating metric {metric['name']}")
    return f"updated metric {metric['name']}"


def _channel(call: Call, project: str, email: str) -> tuple[str, str]:
    url = f"{MONITORING}/projects/{project}/notificationChannels"
    found = _ok(
        call("GET", url, {"filter": f'type="email" AND labels.email_address="{email}"'}, None),
        "listing channels",
    ).get("notificationChannels", [])
    if found:
        return found[0]["name"], f"kept email channel for {email}"
    body = {"type": "email", "displayName": f"Alerts: {email}", "labels": {"email_address": email}}
    made = _ok(call("POST", url, None, body), f"creating channel for {email}")
    return made["name"], f"created email channel for {email}"


def _policy(call: Call, project: str, policy: dict, channel: str) -> str:
    url = f"{MONITORING}/projects/{project}/alertPolicies"
    policy = {**policy, "notificationChannels": [channel]}
    name = policy["displayName"]
    found = _ok(
        call("GET", url, {"filter": f'display_name="{name}"'}, None), "listing alert policies"
    ).get("alertPolicies", [])
    if found:
        # No update mask: the whole policy is replaced by the file's.
        _ok(call("PATCH", f"{MONITORING}/{found[0]['name']}", None, policy), f"updating {name}")
        return f"updated alert “{name}”"
    _ok(call("POST", url, None, policy), f"creating {name}")
    return f"created alert “{name}”"


def apply(call: Call, project: str, email: str, files: Path = FILES) -> list[str]:
    """Metrics first: a policy may watch one."""
    changes = [
        _metric(call, project, json.loads(f.read_text()))
        for f in sorted(files.glob("*.metric.json"))
    ]
    channel, note = _channel(call, project, email)
    changes.append(note)
    changes += [
        _policy(call, project, json.loads(f.read_text()), channel)
        for f in sorted(files.glob("*.policy.json"))
    ]
    return changes


def _google(project: str) -> Call:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    # Your own sign-in has no project of its own to bill API calls to.
    session.headers["x-goog-user-project"] = project

    def call(method: str, url: str, query: dict | None, body: dict | None) -> tuple[int, dict]:
        response = session.request(method, url, params=query, json=body)
        return response.status_code, (response.json() if response.content else {})

    return call


def main() -> None:
    parser = argparse.ArgumentParser(description="Email alerts for the live site")
    parser.add_argument("--email", required=True, help="who gets the alerts")
    parser.add_argument("--project", default=PROJECT)
    args = parser.parse_args()
    for change in apply(_google(args.project), args.project, args.email):
        print(change)


if __name__ == "__main__":
    main()
