"""Pin the account-level failure governance: soft backoff, breaker, degrade.

Repeated soft limits used to get the same short cooldown every time, so an
account that was clearly being throttled kept getting handed out; hard and
unknown failures had no accumulated penalty at all. The panel project's pool
cools a soft-limited credential exponentially (10m, 20m, ... capped at 2h),
trips a breaker after 3 consecutive hard failures (30m doubling to 6h) and
degrades after 5 unknown ones (10m doubling to 2h). A served request clears
everything.

No network: accounts are built from dicts and written to a temp directory.
"""
import base64
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="wb-pool-backoff-")
os.environ["ACCOUNTS_DIR"] = os.path.join(_TMP, "accounts")
os.makedirs(os.environ["ACCOUNTS_DIR"], exist_ok=True)

import wb_accounts as A
import wb_proxy


INTL_ISS = "https://www.workbuddy.ai/auth/realms/copilot"


def jwt(iss=INTL_ISS, sub="u-1"):
    def part(obj):
        raw = base64.urlsafe_b64encode(json.dumps(obj).encode("utf-8")).decode("ascii")
        return raw.rstrip("=")
    return "%s.%s.sig" % (part({"alg": "RS256", "typ": "JWT"}),
                          part({"iss": iss, "sub": sub, "exp": 4102444800}))


def load_account(uid="u-backoff-1"):
    directory = os.path.join(_TMP, uid)
    os.makedirs(directory, exist_ok=True)
    data = {"uid": uid, "domain": "www.workbuddy.ai", "realm": "intl",
            "accessToken": jwt()}
    with open(os.path.join(directory, uid + ".json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    accounts = A.AccountPool(directory).load()
    assert len(accounts) == 1
    return accounts[0]


class BackoffMathTests(unittest.TestCase):
    def test_soft_backoff_doubles_and_caps(self):
        self.assertEqual(A.soft_backoff(1), A.SOFT_RATE_BASE)
        self.assertEqual(A.soft_backoff(2), A.SOFT_RATE_BASE * 2)
        self.assertEqual(A.soft_backoff(4), A.SOFT_RATE_BASE * 8)
        self.assertEqual(A.soft_backoff(50), A.SOFT_RATE_MAX)

    def test_breaker_starts_at_the_threshold_and_caps(self):
        self.assertEqual(A.breaker_backoff(A.BREAKER_THRESHOLD), A.BREAKER_COOLDOWN)
        self.assertEqual(A.breaker_backoff(A.BREAKER_THRESHOLD + 1),
                         A.BREAKER_COOLDOWN * 2)
        self.assertEqual(A.breaker_backoff(99), A.BREAKER_COOLDOWN_MAX)

    def test_degrade_starts_at_the_threshold_and_caps(self):
        self.assertEqual(A.degrade_backoff(A.DEGRADE_THRESHOLD), A.DEGRADE_COOLDOWN)
        self.assertEqual(A.degrade_backoff(A.DEGRADE_THRESHOLD + 2),
                         A.DEGRADE_COOLDOWN * 4)
        self.assertEqual(A.degrade_backoff(99), A.DEGRADE_COOLDOWN_MAX)

    def test_a_parser_miss_is_not_account_level_evidence(self):
        """Failing to read a reset clock must not park the whole credential.

        This used to be `rate_limit_is_account_level(d, None) == True`, which
        made the parser boundary the classification boundary: an intl 429 with
        an unexpected reset shape (or an empty body) bought the credential a
        600s cooldown doubling to 7200s, so a handful of them left a whole realm
        cooling while the panel test still reported the credential healthy.
        """
        intl = ('{"code":6004,"message":"your usage will reset at '
                '2026-10-09 14:44:59 UTC+8"}')
        cn = ('{"code":6004,"msg":"您的使用量已超出频率限制，'
              '将在 2026-10-09 14:44:59 UTC+8 重置。"}')
        for detail in (intl, cn):
            reset_at = wb_proxy.parse_rate_limit_reset(detail)
            self.assertIsNotNone(reset_at, detail)
            self.assertFalse(wb_proxy.rate_limit_is_account_level(detail, reset_at), detail)
        # The incident shape: a model-scoped 429 whose reset wording the parser
        # does not know.
        unparsed = '{"code":6004,"message":"usage exceeds frequency limit, retry later"}'
        self.assertIsNone(wb_proxy.parse_rate_limit_reset(unparsed))
        self.assertFalse(wb_proxy.rate_limit_is_account_level(unparsed, None))
        # Nor is a body we cannot read at all.
        self.assertFalse(wb_proxy.rate_limit_is_account_level("", None))
        self.assertFalse(wb_proxy.rate_limit_is_account_level('{"code":429}', None))

    def test_only_credential_wording_is_account_level(self):
        """Positive evidence keeps the 10m -> 2h ladder reachable.

        Provisional by design: the list is short because the captured intl
        account-level body was not in hand when this was written.
        """
        self.assertTrue(wb_proxy.rate_limit_is_account_level(
            '{"message":"too many requests for this account"}', None))
        self.assertTrue(wb_proxy.rate_limit_is_account_level(
            '{"msg":"该账号请求过于频繁"}', None))
        # A reset clock still wins - that is the model-scoped form.
        self.assertFalse(wb_proxy.rate_limit_is_account_level(
            '{"message":"account rate limit, reset at 2026-10-09 12:00:00 UTC"}',
            time.time() + 60))

    def test_a_genuine_account_level_429_still_backs_off(self):
        account = load_account("u-account-level")
        self.assertTrue(wb_proxy.rate_limit_is_account_level(
            '{"message":"too many requests for this account"}', None))
        self.assertEqual(account.note_soft_rate("HTTP 429 (account soft rate)"),
                         A.SOFT_RATE_BASE)
        self.assertEqual(account.note_soft_rate("HTTP 429 (account soft rate)"),
                         A.SOFT_RATE_BASE * 2)
        self.assertEqual(account.soft_streak, 2)

    def test_reset_clock_is_parsed_for_both_realm_wordings(self):
        cn = ('{"code":6004,"msg":"您的使用量已超出频率限制，'
              '将在 2026-10-09 14:44:59 UTC+8 重置。"}')
        intl = ('{"code":6004,"message":"your usage will reset at '
                '2026-10-09 14:44:59 UTC+8"}')
        cn_reset = wb_proxy.parse_rate_limit_reset(cn)
        self.assertEqual(cn_reset, wb_proxy.parse_rate_limit_reset(intl))
        self.assertIsNotNone(cn_reset)
        # 14:44:59 UTC+8 is the same wall clock as 06:44:59 UTC.
        self.assertEqual(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(cn_reset)),
                         "2026-10-09 06:44:59")
        self.assertIsNone(wb_proxy.parse_rate_limit_reset('{"code":429}'))


class AccountGovernanceTests(unittest.TestCase):
    def test_soft_rate_backs_off_and_counts_the_streak(self):
        account = load_account("u-soft")
        first = account.note_soft_rate("HTTP 429 (account soft rate)")
        second = account.note_soft_rate("HTTP 429 (account soft rate)")
        self.assertEqual(account.soft_streak, 2)
        self.assertEqual(first, A.SOFT_RATE_BASE)
        self.assertEqual(second, A.SOFT_RATE_BASE * 2)
        self.assertGreater(account.throttle_wait(), 0)
        view = account.public()
        self.assertEqual(view["softStreak"], 2)
        self.assertTrue(view["inCooldown"])

    def test_breaker_needs_three_hard_failures(self):
        account = load_account("u-breaker")
        account.note_failure("HTTP 502")
        account.note_failure("HTTP 502")
        self.assertEqual(account.throttle_wait(), 0)
        account.note_failure("HTTP 503")
        self.assertGreater(account.breaker_until, 0)
        self.assertGreater(account.throttle_wait(), 0)
        self.assertTrue(account.public()["breakerFor"])

    def test_unknown_failures_degrade_after_the_threshold(self):
        account = load_account("u-degrade")
        account.note_unknown_failure("connection: TimeoutError")
        account.note_unknown_failure("connection: TimeoutError")
        self.assertEqual(account.throttle_wait(), 0)
        # Unknown failures also feed the shared breaker counter, so the wrap
        # is asserted past both thresholds; the degrade window itself starts
        # at DEGRADE_THRESHOLD.
        for _ in range(A.DEGRADE_THRESHOLD - 2):
            account.note_unknown_failure("connection: TimeoutError")
        self.assertEqual(account.degrade_count, A.DEGRADE_THRESHOLD)
        self.assertGreater(account.degrade_until, 0)
        self.assertGreater(account.throttle_wait(), 0)
        self.assertTrue(account.public()["degradeFor"])

    def test_success_clears_every_penalty(self):
        account = load_account("u-success")
        account.note_soft_rate("HTTP 429 (account soft rate)")
        for _ in range(A.BREAKER_THRESHOLD):
            account.note_failure("HTTP 502")
        account.note_unknown_failure("connection: TimeoutError")
        account.note_success(model="deepseek-v4.1-flash")
        self.assertEqual(account.throttle_wait(), 0)
        self.assertEqual(account.soft_streak, 0)
        self.assertEqual(account.fails, 0)
        self.assertEqual(account.degrade_count, 0)
        self.assertEqual(account.breaker_until, 0.0)
        self.assertEqual(account.degrade_until, 0.0)
        self.assertEqual(account.public()["lastError"], "")


class PanelTestSuccessTests(unittest.TestCase):
    """A green panel test is a served request, so it must clear the streak.

    /accounts/test calls clear_error() on success, which clears the visible
    cooldown fields but never touched soft_streak - the counter note_success()
    resets. The panel could therefore show an account as usable while the next
    account-level 429 resumed the backoff ladder from the stale streak.
    """

    class _Route(object):
        """Just enough handler for the real _route_accounts_test()."""

        def _json(self, code, obj):
            self.code, self.body = code, obj
            return code, obj

    class _Response(object):
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def _drive_panel_test(self, account):
        """Run the real route with a stubbed upstream answer."""
        class Pool(object):
            def get(self, uid):
                return account if uid == account.uid else None

        route = self._Route()
        old = (wb_proxy.POOL, A.urlopen, wb_proxy.aggregate_stream)
        wb_proxy.POOL = Pool()
        A.urlopen = lambda *args, **kwargs: self._Response()
        wb_proxy.aggregate_stream = lambda resp, model, key: {
            "choices": [{"message": {"content": "OK"}}]}
        try:
            return wb_proxy.Handler._route_accounts_test(route, {"uid": account.uid})
        finally:
            wb_proxy.POOL, A.urlopen, wb_proxy.aggregate_stream = old

    def test_a_successful_panel_test_clears_the_streak(self):
        account = load_account("u-panel-test")
        account.note_soft_rate("HTTP 429 (account soft rate)")
        account.note_soft_rate("HTTP 429 (account soft rate)")
        self.assertEqual(account.soft_streak, 2)

        code, body = self._drive_panel_test(account)

        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(account.soft_streak, 0)
        self.assertEqual(account.throttle_wait(), 0)
        self.assertEqual(account.public()["softStreak"], 0)

    def test_a_stale_streak_does_not_resume_on_the_next_event(self):
        account = load_account("u-panel-test-stale")
        for _ in range(3):
            account.note_soft_rate("HTTP 429 (account soft rate)")
        self.assertEqual(account.soft_streak, 3)

        self._drive_panel_test(account)

        # The next account-level 429 starts the ladder over rather than
        # continuing from the streak the panel test should have cleared.
        wait = account.note_soft_rate("HTTP 429 (account soft rate)")
        self.assertEqual(account.soft_streak, 1)
        self.assertEqual(wait, A.SOFT_RATE_BASE)

    def test_a_panel_test_keeps_other_models_throttled(self):
        """The narrow success path must not lift sibling model cooldowns."""
        account = load_account("u-panel-test-siblings")
        account.note_error("HTTP 429 (model throttled)", model="glm-5.3",
                           cooldown=600)

        self._drive_panel_test(account)

        self.assertFalse(account.ready(model="glm-5.3"))
        self.assertIn("glm-5.3", [item["model"]
                                  for item in account.public()["modelCooldowns"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
