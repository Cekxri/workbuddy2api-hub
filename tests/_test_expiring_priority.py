"""临期积分优先分派：快到期的积分先被消耗。

分派原本是纯轮询。加了这条偏好之后，活跃积分包进入窗口（默认 7 天）的账号
先被交出去，窗口内按到期先后使用，同一天到期的账号之间仍轮询——所以既要证明
「临期账号确实被优先」，也要证明「没有临期账号时行为与原来完全一致」，还要
证明「看不懂的积分数据不会被当成临期」。

Run with the current interpreter (python tests/run_all.py expiring).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wb_accounts
import wb_settings


def make_account(uid, realm="cn", credits=None, **extra):
    data = {"uid": uid, "accessToken": "token-%s" % uid, "realm": realm}
    if credits is not None:
        data["credits"] = credits
    data.update(extra)
    return wb_accounts.Account(data)


def credits(*days, package_code="package", remain=100):
    """A credits blob whose packages expire in the given days.

    A None day stands for a package the upstream gave no end date for.
    """
    packages = []
    for index, day in enumerate(days):
        packages.append({
            "name": "pkg%d" % index,
            "package_code": package_code,
            "remain": remain,
            "used": 0,
            "size": remain,
            "days_left": day,
            "is_expired": day is not None and day < 0,
        })
    total = remain * len(packages)
    return {"remain": total, "used": 0, "size": total, "packages": packages}


class ExpiringWindowSettingTests(unittest.TestCase):
    def test_default_is_seven_days(self):
        with tempfile.TemporaryDirectory(prefix="expiry-setting-") as directory:
            self.assertEqual(wb_settings.expiring_window_days(directory), 7)
            snapshot = wb_settings.limits_snapshot(directory)
            self.assertEqual(snapshot["expiring_window_days"]["global"], 7)

    def test_round_trip_and_explicit_off_survives_reread(self):
        with tempfile.TemporaryDirectory(prefix="expiry-setting-") as directory:
            self.assertEqual(wb_settings.set_expiring_window_days(directory, 0), 0)
            # 显式写 0 表示「关」，重读时不能被默认值 7 顶回来。
            self.assertEqual(wb_settings.expiring_window_days(directory), 0)
            self.assertEqual(wb_settings.set_expiring_window_days(directory, 3), 3)
            self.assertEqual(wb_settings.expiring_window_days(directory), 3)

    def test_other_guards_still_default_to_off(self):
        with tempfile.TemporaryDirectory(prefix="expiry-setting-") as directory:
            self.assertEqual(wb_settings.reserve_credits(directory), 0)
            self.assertEqual(wb_settings.daily_credit_limit(directory), 0)
            self.assertEqual(wb_settings.model_daily_token_limit(directory), 0)


class SoonestExpiringTests(unittest.TestCase):
    def test_picks_the_earliest_live_package(self):
        account = make_account("u1", credits=credits(9, 2.5, 4))
        self.assertEqual(account.soonest_expiring_days(), 2.5)

    def test_skips_expired_and_empty_packages(self):
        blob = credits(-1, 3)
        blob["packages"][1]["remain"] = 0
        account = make_account("u2", credits=blob)
        self.assertIsNone(account.soonest_expiring_days())

    def test_skips_the_enterprise_quota(self):
        # 企业额度的 cycleEndTime 是周期重置（额度回满），不是积分作废，
        # 拿它当临期信号会让企业账号永远「即将到期」。
        account = make_account("u3", credits=credits(1, package_code="enterprise"))
        self.assertIsNone(account.soonest_expiring_days())

    def test_unknown_data_is_not_a_preference(self):
        self.assertIsNone(make_account("u4").soonest_expiring_days())
        self.assertIsNone(make_account("u5", credits={}).soonest_expiring_days())
        self.assertIsNone(make_account("u6", credits=credits(None)).soonest_expiring_days())


class InWindowTests(unittest.TestCase):
    def test_window_boundaries(self):
        account = make_account("w1", credits=credits(7))
        account.expiring_window_days = 7
        self.assertTrue(account.in_expiring_window())
        account.expiring_window_days = 6
        self.assertFalse(account.in_expiring_window())

    def test_window_off_and_unknown_are_never_urgent(self):
        off = make_account("w2", credits=credits(1))
        off.expiring_window_days = 0
        self.assertFalse(off.in_expiring_window())

        unknown = make_account("w3")
        unknown.expiring_window_days = 7
        self.assertFalse(unknown.in_expiring_window())


class PickPrefersExpiringTests(unittest.TestCase):
    def _pool(self, accounts, window=7):
        directory = tempfile.mkdtemp(prefix="expiry-pool-")
        pool = wb_accounts.AccountPool(directory, log=lambda _m: None)
        pool.accounts = accounts
        pool.apply_expiring_window({"global": window, "intl": window, "cn": window})
        return pool

    def test_window_account_takes_every_pick(self):
        soon = make_account("soon", credits=credits(2))
        later = make_account("later", credits=credits(40))
        pool = self._pool([later, soon])
        self.assertEqual({pool.pick(realm="cn").uid for _ in range(6)}, {"soon"})

    def test_earliest_bucket_wins_over_a_later_one(self):
        in_two = make_account("in-two", credits=credits(2))
        in_five = make_account("in-five", credits=credits(5))
        pool = self._pool([in_five, in_two])
        self.assertEqual({pool.pick(realm="cn").uid for _ in range(4)}, {"in-two"})

    def test_same_day_accounts_still_take_turns(self):
        # 同一天到期的两个账号之间必须轮询，否则一拨流量会全压在单个账号上。
        first = make_account("same-a", credits=credits(3.2))
        second = make_account("same-b", credits=credits(3.8))
        pool = self._pool([first, second])
        picked = [pool.pick(realm="cn").uid for _ in range(4)]
        self.assertEqual(sorted(set(picked)), ["same-a", "same-b"])
        self.assertEqual(picked, ["same-a", "same-b", "same-a", "same-b"])

    def test_no_window_account_keeps_the_plain_round_robin(self):
        a = make_account("plain-a", credits=credits(40))
        b = make_account("plain-b", credits=credits(50))
        pool = self._pool([a, b])
        picked = [pool.pick(realm="cn").uid for _ in range(4)]
        self.assertEqual(sorted(set(picked)), ["plain-a", "plain-b"])

    def test_window_off_keeps_the_plain_round_robin(self):
        soon = make_account("off-soon", credits=credits(1))
        later = make_account("off-later", credits=credits(40))
        pool = self._pool([soon, later], window=0)
        picked = {pool.pick(realm="cn").uid for _ in range(4)}
        self.assertEqual(picked, {"off-soon", "off-later"})

    def test_unavailable_window_account_falls_back_to_the_pool(self):
        # 临期账号这一刻被保留积分挡住时，请求要落到普通账号上，而不是空转。
        parked = make_account("parked", credits=credits(2))
        parked.reserve_credits = 1000
        later = make_account("spare", credits=credits(40))
        pool = self._pool([parked, later])
        self.assertEqual({pool.pick(realm="cn").uid for _ in range(4)}, {"spare"})

    def test_excluded_window_account_falls_through(self):
        soon = make_account("excl-soon", credits=credits(1))
        later = make_account("excl-later", credits=credits(40))
        pool = self._pool([soon, later])
        self.assertEqual(pool.pick(realm="cn", exclude={"excl-soon"}).uid, "excl-later")

    def test_realms_are_ranked_separately(self):
        # 国际版临期账号只在国际版里优先，不影响国内版。
        intl_soon = make_account("intl-soon", realm="intl", credits=credits(1))
        intl_later = make_account("intl-later", realm="intl", credits=credits(40))
        cn_later = make_account("cn-later", realm="cn", credits=credits(40))
        pool = self._pool([intl_soon, intl_later, cn_later])
        self.assertEqual({pool.pick(realm="intl").uid for _ in range(4)}, {"intl-soon"})
        self.assertEqual({pool.pick(realm="cn").uid for _ in range(4)}, {"cn-later"})


class SessionAffinityTests(unittest.TestCase):
    def _pool(self, accounts):
        directory = tempfile.mkdtemp(prefix="expiry-affinity-")
        pool = wb_accounts.AccountPool(directory, log=lambda _m: None)
        pool.accounts = accounts
        pool.apply_expiring_window({"global": 7, "intl": 7, "cn": 7})
        return pool

    def test_a_bound_session_keeps_its_account(self):
        # 会话亲和优先：已经绑定的账号不会被临期账号抢走。
        bound = make_account("bound", credits=credits(40))
        soon = make_account("bound-soon", credits=credits(1))
        pool = self._pool([bound, soon])
        pool.affinity.bind("s1", "bound")
        for _ in range(4):
            self.assertEqual(
                pool.pick_for_session(realm="cn", session_key="s1").uid, "bound")

    def test_a_fresh_session_lands_on_the_window_account(self):
        bound = make_account("fresh-later", credits=credits(40))
        soon = make_account("fresh-soon", credits=credits(1))
        pool = self._pool([bound, soon])
        self.assertEqual(
            pool.pick_for_session(realm="cn", session_key="s2").uid, "fresh-soon")


class ApplyWindowTests(unittest.TestCase):
    def test_pool_copies_the_setting_onto_every_account(self):
        with tempfile.TemporaryDirectory(prefix="expiry-apply-") as directory:
            wb_settings.set_expiring_window_days(directory, 3)
            pool = wb_accounts.AccountPool(directory, log=lambda _m: None)
            pool.accounts = [make_account("a1"), make_account("a2", realm="intl")]
            pool.apply_expiring_window()
            self.assertEqual([a.expiring_window_days for a in pool.accounts], [3, 3])

    def test_load_applies_the_window(self):
        with tempfile.TemporaryDirectory(prefix="expiry-load-") as directory:
            wb_settings.set_expiring_window_days(directory, 5)
            account = make_account("loaded", credits=credits(4))
            account.path = os.path.join(directory, "loaded.json")
            account.save(directory)
            pool = wb_accounts.AccountPool(directory, log=lambda _m: None)
            pool.load()
            self.assertEqual(pool.accounts[0].expiring_window_days, 5)
            self.assertTrue(pool.accounts[0].in_expiring_window())


if __name__ == "__main__":
    unittest.main(verbosity=2)
