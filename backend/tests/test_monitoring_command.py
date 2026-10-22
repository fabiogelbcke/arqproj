"""The live site's alerts (plan section 21): the command that applies them, and that
what they watch is what the app really logs."""

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.commands import monitoring

SERVICE = Path(__file__).resolve().parents[2] / "deploy" / "production" / "service.yaml"


class FakeGoogle:
    """Monitoring and Logging, as far as the command uses them: in memory."""

    def __init__(self):
        self.metrics: dict[str, dict] = {}
        self.channels: list[dict] = []
        self.policies: list[dict] = []
        self.refuse: str | None = None  # a URL part to answer 403 for
        self.logged_at: list[str] = ["2026-10-22T05:31:06Z"]  # the passes' log lines
        self.log_filters: list[str] = []

    def __call__(self, method, url, query, body):
        if self.refuse and self.refuse in url:
            return 403, {"error": {"message": "Permission denied"}}
        if url.endswith("/entries:list"):
            self.log_filters.append(body["filter"])
            since = re.search(r'timestamp>="([^"]+)"', body["filter"])[1]
            return 200, {"entries": [{"timestamp": t} for t in self.logged_at if t >= since]}
        if "/metrics" in url:
            name = url.rsplit("/", 1)[1]
            if method == "GET":
                return (200, self.metrics[name]) if name in self.metrics else (404, {})
            self.metrics[body["name"]] = body
            return 200, body
        if url.endswith("/notificationChannels"):
            if method == "GET":
                email = re.search(r'email_address="([^"]+)"', query["filter"])[1]
                return 200, {
                    "notificationChannels": [
                        c for c in self.channels if c["labels"]["email_address"] == email
                    ]
                }
            made = {
                **body,
                "name": f"projects/p/notificationChannels/{len(self.channels) + 1}",
                "enabled": True,
            }
            self.channels.append(made)
            return 200, made
        if url.endswith("/alertPolicies"):
            if method == "GET":
                name = re.search(r'display_name="([^"]+)"', query["filter"])[1]
                return 200, {
                    "alertPolicies": [p for p in self.policies if p["displayName"] == name]
                }
            made = {**body, "name": f"projects/p/alertPolicies/{len(self.policies) + 1}"}
            self.policies.append(made)
            return 200, made
        if "/notificationChannels/" in url and method == "PATCH":
            assert query == {"updateMask": "enabled"}
            channel = next(c for c in self.channels if url.endswith(c["name"]))
            channel.update(body)
            return 200, channel
        if "/alertPolicies/" in url and method == "PATCH":
            path = url.split(monitoring.MONITORING + "/", 1)[1]
            index = next(i for i, p in enumerate(self.policies) if p["name"] == path)
            self.policies[index] = {**body, "name": path}
            return 200, self.policies[index]
        raise AssertionError(f"unexpected {method} {url}")


NOW = datetime(2026, 10, 22, 5, 40, tzinfo=UTC)


def test_sets_up_the_metric_the_channel_and_the_alerts_sending_to_it():
    google = FakeGoogle()
    changes = monitoring.apply(google, "p", "ana@alinea.example", now=NOW)
    assert set(google.metrics) == {"portal_maintenance_passes"}
    assert [c["labels"]["email_address"] for c in google.channels] == ["ana@alinea.example"]
    assert {p["displayName"] for p in google.policies} == {
        "portal: an error on the live site",
        "portal: maintenance passes stopped",
    }
    assert all(p["notificationChannels"] == [google.channels[0]["name"]] for p in google.policies)
    # The metric comes before the alert that watches it.
    assert changes[0].startswith("created metric")
    assert monitoring.STOPPED_NOW not in changes  # a pass 9 minutes ago


def test_says_when_passes_have_already_stopped():
    """The "stopped" alert can't report an outage under way when it is installed
    (it needs a pass counted after it exists): the command says so instead."""
    google = FakeGoogle()
    google.logged_at = ["2026-10-22T05:10:00Z"]  # 30 minutes ago
    changes = monitoring.apply(google, "p", "ana@alinea.example", now=NOW)
    assert changes[-1] == monitoring.STOPPED_NOW
    # It asked the logs for the passes' own lines, since 20 minutes ago.
    passes = json.loads((monitoring.FILES / "maintenance-passes.metric.json").read_text())
    assert google.log_filters == [f'{passes["filter"]} AND timestamp>="2026-10-22T05:20:00Z"']


def test_running_again_updates_in_place_and_adds_nothing(tmp_path):
    files = tmp_path / "monitoring"
    shutil.copytree(monitoring.FILES, files)
    google = FakeGoogle()
    monitoring.apply(google, "p", "ana@alinea.example", files, now=NOW)
    first = [p["name"] for p in google.policies]

    errors = files / "errors.policy.json"
    edited = json.loads(errors.read_text())
    edited["alertStrategy"]["notificationRateLimit"]["period"] = "7200s"
    errors.write_text(json.dumps(edited))
    changes = monitoring.apply(google, "p", "ana@alinea.example", files, now=NOW)

    assert [p["name"] for p in google.policies] == first
    assert len(google.channels) == 1
    assert "kept email channel for ana@alinea.example" in changes
    policy = next(p for p in google.policies if p["displayName"] == edited["displayName"])
    assert policy["alertStrategy"]["notificationRateLimit"]["period"] == "7200s"


def test_another_address_gets_its_own_channel():
    google = FakeGoogle()
    monitoring.apply(google, "p", "ana@alinea.example", now=NOW)
    monitoring.apply(google, "p", "caio@alinea.example", now=NOW)
    assert len(google.channels) == 2
    assert all(p["notificationChannels"] == [google.channels[1]["name"]] for p in google.policies)


def test_turns_a_channel_that_was_turned_off_back_on():
    """Off, it forwards nothing: the alerts would look set up and never arrive."""
    google = FakeGoogle()
    monitoring.apply(google, "p", "ana@alinea.example", now=NOW)
    google.channels[0]["enabled"] = False
    changes = monitoring.apply(google, "p", "ana@alinea.example", now=NOW)
    assert google.channels[0]["enabled"] is True
    assert len(google.channels) == 1
    assert "turned the email channel for ana@alinea.example back on" in changes


def test_a_refusal_stops_with_what_failed():
    google = FakeGoogle()
    google.refuse = "/alertPolicies"
    with pytest.raises(
        SystemExit, match="listing alert policies failed \\(403\\): Permission denied"
    ):
        monitoring.apply(google, "p", "ana@alinea.example", now=NOW)


def test_every_alert_watches_the_live_service():
    """A renamed service would leave the alerts watching nothing, silently."""
    service = re.search(r"^  name: (\S+)", SERVICE.read_text(), re.M)[1]
    watched = [
        json.loads(f.read_text())
        for f in [*monitoring.FILES.glob("*.metric.json"), *monitoring.FILES.glob("*.policy.json")]
    ]
    filters = [w["filter"] for w in watched if "filter" in w] + [
        c["conditionMatchedLog"]["filter"]
        for w in watched
        for c in w.get("conditions", [])
        if "conditionMatchedLog" in c
    ]
    assert filters and all(f'service_name="{service}"' in f for f in filters)


def test_the_stopped_alert_watches_the_metric_defined_here():
    metric = json.loads((monitoring.FILES / "maintenance-passes.metric.json").read_text())
    policy = json.loads((monitoring.FILES / "maintenance-stopped.policy.json").read_text())
    watched = policy["conditions"][0]["conditionAbsent"]["filter"]
    assert f'logging.googleapis.com/user/{metric["name"]}"' in watched


def pass_line_pattern() -> str:
    """The text the passes metric looks for in a log line's message."""
    metric = json.loads((monitoring.FILES / "maintenance-passes.metric.json").read_text())
    return re.search(r'jsonPayload\.message:"([^"]+)"', metric["filter"])[1]


def test_the_pass_pattern_tells_a_pass_from_other_lines():
    # Self-test for test_maintenance_scan's check that a real pass's line matches.
    assert pass_line_pattern() in "maintenance: Report(offices=2, projects=4, emails=0)"
    assert pass_line_pattern() not in "maintenance: project a/b failed"
    assert pass_line_pattern() not in "maintenance: out of time, 3 projects left for the next pass"
