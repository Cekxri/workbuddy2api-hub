"""Update discovery: what the gateway may ask GitHub, and what it may keep.

Phase A of the update feature is discovery only - it reports that a newer stable
release exists and stops there. What this suite pins is the contract around it:

  * the daily check is opt-in and off for an install that never set the key;
  * off means no request at all, on means roughly once per 24h, and the manual
    path answers even with the switch off and the window closed;
  * drafts, prereleases, malformed tags and unexpected documents are skipped
    rather than crashing the gateway;
  * a failed check is non-fatal, keeps the last known answer, and reports one
    short line that carries no URL and no response body;
  * the background thread cannot hold the process open.

No network access: every check runs against an injected fetcher.

    python tests/_test_update_check.py
"""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _isolated_dirs import isolated_data_dirs  # noqa: E402  (its own data root)

_TMP = isolated_data_dirs("wb-update-check-")

import wb_proxy as proxy  # noqa: E402
import wb_settings  # noqa: E402
import wb_updates  # noqa: E402

CURRENT = "1.6.17"


def release(tag, **overrides):
    entry = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": "https://github.com/ardeyouxipianyi/workbuddy2api-hub/releases/tag/" + tag,
        "published_at": "2026-10-08T00:00:00Z",
    }
    entry.update(overrides)
    return entry


class FakeFetcher(object):
    """Stands in for the GitHub call and counts how often it was made."""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def __call__(self, url, timeout):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload)


def checker(directory, fetcher, **kwargs):
    kwargs.setdefault("first_delay", 0)
    kwargs.setdefault("poll_seconds", 0.01)
    return wb_updates.UpdateChecker(current_version=CURRENT,
                                    settings_dir=directory,
                                    fetcher=fetcher, **kwargs)


class SettingsContractTests(unittest.TestCase):
    def test_missing_key_reads_as_off(self):
        with tempfile.TemporaryDirectory(prefix="upd-set-") as d:
            self.assertFalse(wb_settings.update_check_enabled(d))
            with mock.patch.object(proxy, "ACCOUNTS_DIR", d):
                self.assertFalse(proxy.runtime_settings_view()["update_check_enabled"])

    def test_enable_and_disable_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="upd-set-") as d:
            self.assertTrue(wb_settings.set_update_check_enabled(d, True))
            self.assertTrue(wb_settings.update_check_enabled(d))
            with open(wb_settings.settings_path(d), encoding="utf-8") as fh:
                self.assertIs(json.load(fh)["update_check_enabled"], True)
            self.assertFalse(wb_settings.set_update_check_enabled(d, False))
            self.assertFalse(wb_settings.update_check_enabled(d))
            with mock.patch.object(proxy, "ACCOUNTS_DIR", d):
                self.assertFalse(proxy.runtime_settings_view()["update_check_enabled"])

    def test_only_a_real_true_enables_it(self):
        # A hand-edited "yes" or 1 must not start a daily outbound request.
        for value in ("yes", 1, "true", [1], {"on": True}):
            with tempfile.TemporaryDirectory(prefix="upd-set-") as d:
                wb_settings.save(d, {"update_check_enabled": value})
                self.assertFalse(wb_settings.update_check_enabled(d), value)


class VersionComparisonTests(unittest.TestCase):
    def test_plain_semver_parses_with_or_without_the_v(self):
        self.assertEqual(wb_updates.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(wb_updates.parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(wb_updates.parse_version(" v10.0.4 "), (10, 0, 4))

    def test_unorderable_tags_are_rejected(self):
        for tag in ("v1.2", "v1.2.3.4", "v1.2.3-rc1", "nightly", "", None, "v1.x.3"):
            self.assertIsNone(wb_updates.parse_version(tag), tag)

    def test_is_newer_orders_three_parts(self):
        self.assertTrue(wb_updates.is_newer("1.6.18", "1.6.17"))
        self.assertTrue(wb_updates.is_newer("v1.7.0", "1.6.99"))
        self.assertTrue(wb_updates.is_newer("2.0.0", "1.99.99"))
        self.assertFalse(wb_updates.is_newer("1.6.17", "1.6.17"))
        self.assertFalse(wb_updates.is_newer("1.6.16", "1.6.17"))
        self.assertFalse(wb_updates.is_newer("garbage", "1.6.17"))


class ReleasePickingTests(unittest.TestCase):
    def test_newer_stable_release_wins(self):
        picked = wb_updates.pick_latest([release("v1.6.18")], CURRENT)
        self.assertEqual(picked["version"], "1.6.18")
        self.assertTrue(picked["newer"])
        self.assertTrue(picked["url"].startswith("https://github.com/"))

    def test_same_and_older_releases_are_not_an_update(self):
        for tag in ("v1.6.17", "v1.6.16", "v1.0.0"):
            self.assertFalse(wb_updates.pick_latest([release(tag)], CURRENT)["newer"], tag)

    def test_drafts_and_prereleases_are_ignored(self):
        document = [
            release("v9.9.9", draft=True),
            release("v8.8.8", prerelease=True),
            release("v1.6.18"),
        ]
        self.assertEqual(wb_updates.pick_latest(document, CURRENT)["version"], "1.6.18")

    def test_only_drafts_and_prereleases_means_no_known_latest(self):
        document = [release("v9.9.9", draft=True), release("v8.8.8", prerelease=True)]
        self.assertIsNone(wb_updates.pick_latest(document, CURRENT))

    def test_malformed_entries_are_skipped_not_fatal(self):
        document = [
            "not a release",
            None,
            17,
            {},
            {"tag_name": None},
            {"tag_name": "nightly"},
            {"tag_name": "v1.6.18", "draft": "yes-please"},
            release("v1.6.19"),
        ]
        self.assertEqual(wb_updates.pick_latest(document, CURRENT)["version"], "1.6.19")

    def test_the_highest_version_wins_not_the_first(self):
        document = [release("v1.6.18"), release("v1.9.0"), release("v1.7.5")]
        self.assertEqual(wb_updates.pick_latest(document, CURRENT)["version"], "1.9.0")

    def test_a_non_list_document_picks_nothing(self):
        for document in ({}, {"releases": []}, "text", None):
            self.assertIsNone(wb_updates.pick_latest(document, CURRENT), document)

    def test_release_url_is_restricted_to_github_https(self):
        for bad in ("javascript:alert(1)", "http://github.com/x", "data:text/html,x", ""):
            self.assertEqual(wb_updates.safe_url(bad), "", bad)
        self.assertEqual(wb_updates.safe_url("https://github.com/a/b"),
                         "https://github.com/a/b")


class CheckBehaviourTests(unittest.TestCase):
    def test_disabled_mode_sends_no_request(self):
        with tempfile.TemporaryDirectory(prefix="upd-run-") as d:
            fetcher = FakeFetcher([release("v1.6.18")])
            checker_ = checker(d, fetcher)
            status = checker_.check()
            self.assertEqual(fetcher.calls, [])
            self.assertEqual(status["skipped"], "disabled")
            self.assertFalse(status["enabled"])
            self.assertIsNone(status["latest_version"])

    def test_enabled_mode_respects_the_24h_gate(self):
        with tempfile.TemporaryDirectory(prefix="upd-run-") as d:
            wb_settings.set_update_check_enabled(d, True)
            fetcher = FakeFetcher([release("v1.6.18")])
            checker_ = checker(d, fetcher)
            first = checker_.check()
            self.assertEqual(len(fetcher.calls), 1)
            self.assertTrue(first["update_available"])
            self.assertEqual(first["latest_version"], "1.6.18")
            second = checker_.check()
            self.assertEqual(len(fetcher.calls), 1, "a second pass must wait out the window")
            self.assertEqual(second["skipped"], "not due yet")

    def test_the_window_opens_after_a_day(self):
        with tempfile.TemporaryDirectory(prefix="upd-run-") as d:
            wb_settings.set_update_check_enabled(d, True)
            fetcher = FakeFetcher([release("v1.6.18")])
            checker_ = checker(d, fetcher)
            checker_.check()
            checker_._last_attempt = time.time() - wb_updates.SCHEDULED_INTERVAL_SECONDS - 1
            self.assertTrue(checker_.due())
            checker_.check()
            self.assertEqual(len(fetcher.calls), 2)

    def test_manual_check_ignores_the_switch_and_the_window(self):
        with tempfile.TemporaryDirectory(prefix="upd-run-") as d:
            fetcher = FakeFetcher([release("v1.6.18")])
            checker_ = checker(d, fetcher)
            checker_.check()                      # disabled: nothing sent
            self.assertEqual(fetcher.calls, [])
            status = checker_.check(manual=True)  # the operator asked anyway
            self.assertEqual(len(fetcher.calls), 1)
            self.assertTrue(status["update_available"])
            checker_.check(manual=True)
            self.assertEqual(len(fetcher.calls), 2, "manual bypasses the 24h gate too")

    def test_scheduled_pass_with_nothing_newer_reports_false(self):
        with tempfile.TemporaryDirectory(prefix="upd-run-") as d:
            wb_settings.set_update_check_enabled(d, True)
            fetcher = FakeFetcher([release("v1.6.17"), release("v1.6.10")])
            status = checker(d, fetcher).check()
            self.assertEqual(len(fetcher.calls), 1)
            self.assertFalse(status["update_available"])
            self.assertEqual(status["latest_version"], "1.6.17")
            self.assertEqual(status["last_error"], "")

    def test_cadence_survives_a_restart(self):
        with tempfile.TemporaryDirectory(prefix="upd-run-") as d:
            wb_settings.set_update_check_enabled(d, True)
            fetcher = FakeFetcher([release("v1.6.18")])
            checker(d, fetcher).check()
            # A new process reads the stored attempt time, so a restart is not
            # an excuse to check again.
            revived = checker(d, FakeFetcher([release("v1.6.18")]))
            self.assertFalse(revived.due())
            self.assertEqual(revived.status()["latest_version"], "1.6.18")
            self.assertTrue(revived.status()["update_available"])


class FailureHandlingTests(unittest.TestCase):
    def _failing(self, directory, error):
        fetcher = FakeFetcher(error=error)
        status = checker(directory, fetcher).check(manual=True)
        return fetcher, status

    def test_http_error_is_reported_without_the_body(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            error = urllib.error.HTTPError(
                wb_updates.RELEASES_URL, 403, "rate limited",
                {"X-Secret-Header": "leak-me"}, None)
            _fetcher, status = self._failing(d, error)
            self.assertEqual(status["last_error"], "HTTP 403")
            self.assertFalse(status["update_available"])
            self.assertIsNone(status["latest_version"])

    def test_network_error_is_non_fatal(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            error = urllib.error.URLError("temporary failure in name resolution")
            _fetcher, status = self._failing(d, error)
            self.assertEqual(status["last_error"], "network error: URLError")
            self.assertFalse(status["checking"])

    def test_invalid_json_is_non_fatal(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            fetcher = FakeFetcher("{ this is not json")
            status = checker(d, fetcher).check(manual=True)
            self.assertEqual(len(fetcher.calls), 1)
            self.assertEqual(status["last_error"], "invalid JSON")

    def test_an_unexpected_document_is_non_fatal(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            status = checker(d, FakeFetcher({"message": "Not Found"})).check(manual=True)
            self.assertEqual(status["last_error"], "unexpected release document")

    def test_a_failed_check_keeps_the_last_known_answer(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            wb_settings.set_update_check_enabled(d, True)
            checker_ = checker(d, FakeFetcher([release("v1.6.18")]))
            checker_.check()
            checker_._fetch = FakeFetcher(error=urllib.error.URLError("down"))
            checker_._last_attempt = 0
            status = checker_.check()
            self.assertEqual(status["last_error"], "network error: URLError")
            self.assertEqual(status["latest_version"], "1.6.18")
            self.assertTrue(status["update_available"])

    def test_no_url_or_body_reaches_the_settings_file(self):
        marker = "SECRET-BODY-MARKER"
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            error = urllib.error.URLError("failed for https://api.github.com/x?token=" + marker)
            checker(d, FakeFetcher(error=error)).check(manual=True)
            with open(wb_settings.settings_path(d), encoding="utf-8") as fh:
                raw = fh.read()
        self.assertNotIn(marker, raw)
        self.assertNotIn("api.github.com", raw)
        self.assertNotIn("https://", raw)

    def test_only_operational_fields_are_persisted(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            wb_settings.set_update_check_enabled(d, True)
            checker(d, FakeFetcher([release("v1.6.18")])).check()
            with open(wb_settings.settings_path(d), encoding="utf-8") as fh:
                stored = json.load(fh)
        self.assertEqual(sorted(stored["update_check"]),
                         ["last_attempt", "last_success", "latest_version"])
        self.assertEqual(stored["update_check"]["latest_version"], "1.6.18")

    def test_a_failed_attempt_is_not_recorded_as_a_success(self):
        with tempfile.TemporaryDirectory(prefix="upd-fail-") as d:
            checker(d, FakeFetcher(error=urllib.error.URLError("down"))).check(manual=True)
            state = wb_settings.update_check_state(d)
        self.assertGreater(state["last_attempt"], 0)
        self.assertEqual(state["last_success"], 0.0)
        self.assertEqual(state["latest_version"], "")


class BackgroundWorkerTests(unittest.TestCase):
    def test_the_worker_is_a_daemon_and_stops_promptly(self):
        with tempfile.TemporaryDirectory(prefix="upd-bg-") as d:
            worker = checker(d, FakeFetcher([release("v1.6.18")]),
                             first_delay=3600, poll_seconds=3600)
            self.assertTrue(worker.daemon, "a non-daemon thread would hold the process open")
            worker.start()
            worker.stop()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

    def test_a_disabled_worker_never_fetches(self):
        with tempfile.TemporaryDirectory(prefix="upd-bg-") as d:
            fetcher = FakeFetcher([release("v1.6.18")])
            worker = checker(d, fetcher)
            worker.start()
            time.sleep(0.2)
            worker.stop()
            worker.join(timeout=5)
        self.assertEqual(fetcher.calls, [], "the switch is off: no background request")

    def test_an_enabled_worker_checks_on_its_own(self):
        with tempfile.TemporaryDirectory(prefix="upd-bg-") as d:
            wb_settings.set_update_check_enabled(d, True)
            fetcher = FakeFetcher([release("v1.6.18")])
            worker = checker(d, fetcher)
            worker.start()
            deadline = time.time() + 5
            while not fetcher.calls and time.time() < deadline:
                time.sleep(0.02)
            worker.stop()
            worker.join(timeout=5)
        self.assertGreaterEqual(len(fetcher.calls), 1)
        self.assertFalse(worker.is_alive())


class RouteTests(unittest.TestCase):
    class Request(object):
        _handle_settings_save = proxy.Handler._handle_settings_save
        _get_updates = proxy.Handler._get_updates
        _route_update_check = proxy.Handler._route_update_check

        def __init__(self, payload=None):
            self.payload = payload
            self.status = None
            self.reply = None

        def _payload_or_error(self, allow_list=False):
            return self.payload

        def _authorized(self):
            return True

        def _panel_ok(self):
            return True

        def _error(self, status, message, kind=""):
            self.status = status
            self.reply = message
            return status, message

        def _json(self, status, payload):
            self.status = status
            self.reply = payload
            return status, payload

    def _save(self, directory, payload, updates=None):
        request = self.Request(payload)
        with mock.patch.multiple(proxy, ACCOUNTS_DIR=directory, UPDATES=updates):
            request._handle_settings_save()
        return request

    def test_settings_save_toggles_the_switch(self):
        with tempfile.TemporaryDirectory(prefix="upd-route-") as d:
            request = self._save(d, {"update_check_enabled": True})
            self.assertEqual(request.status, 200)
            self.assertIs(request.reply["update_check_enabled"], True)
            self.assertTrue(wb_settings.update_check_enabled(d))
            request = self._save(d, {"update_check_enabled": False})
            self.assertFalse(wb_settings.update_check_enabled(d))

    def test_settings_save_refuses_a_non_boolean(self):
        with tempfile.TemporaryDirectory(prefix="upd-route-") as d:
            for value in ("false", 0, 1, None, "yes"):
                request = self._save(d, {"update_check_enabled": value})
                self.assertEqual(request.status, 400, value)
            self.assertFalse(wb_settings.update_check_enabled(d))

    def test_turning_it_on_wakes_a_parked_worker(self):
        with tempfile.TemporaryDirectory(prefix="upd-route-") as d:
            worker = checker(d, FakeFetcher([release("v1.6.18")]),
                             first_delay=3600, poll_seconds=3600)
            worker.start()
            try:
                self._save(d, {"update_check_enabled": True}, updates=worker)
                self.assertTrue(worker._wake.is_set())
            finally:
                worker.stop()
                worker.join(timeout=5)

    def test_the_status_route_reports_without_checking(self):
        with tempfile.TemporaryDirectory(prefix="upd-route-") as d:
            fetcher = FakeFetcher([release("v1.6.18")])
            worker = checker(d, fetcher)
            with mock.patch.object(proxy, "UPDATES", worker):
                request = self.Request()
                request._get_updates()
            self.assertEqual(request.status, 200)
            self.assertEqual(request.reply["current_version"], proxy.running_version())
            self.assertFalse(request.reply["update_available"])
            self.assertEqual(fetcher.calls, [], "a status read must not spend a request")

    def test_the_manual_route_runs_a_check_and_answers_with_it(self):
        with tempfile.TemporaryDirectory(prefix="upd-route-") as d:
            fetcher = FakeFetcher([release("v1.6.18")])
            worker = checker(d, fetcher)
            with mock.patch.object(proxy, "UPDATES", worker):
                request = self.Request()
                request._route_update_check()
            self.assertEqual(request.status, 200)
            self.assertIs(request.reply["ok"], True)
            self.assertEqual(request.reply["latest_version"], "1.6.18")
            self.assertTrue(request.reply["update_available"])
            self.assertEqual(len(fetcher.calls), 1)

    def test_the_status_route_still_answers_without_a_worker(self):
        with tempfile.TemporaryDirectory(prefix="upd-route-") as d:
            with mock.patch.multiple(proxy, UPDATES=None, ACCOUNTS_DIR=d):
                request = self.Request()
                request._get_updates()
            self.assertEqual(request.status, 200)
            self.assertFalse(request.reply["update_available"])
            self.assertEqual(request.reply["msg"], "更新检查未运行")


if __name__ == "__main__":
    unittest.main(verbosity=2)
