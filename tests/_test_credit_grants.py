"""积分获取历史：把账号积分快照摊平成发放记录（GET /accounts/credits/grants）。

上游对每个账号返回一份积分包清单（免费套餐、每日活跃奖励的 Bonus Pack、活动包…），
每个包带面额、发放时间与到期时间。这个接口只读内存里的快照，**不发上游请求**，所以
套件钉住：

  - 状态判定顺序（过期 > 用完 > 在扣减 > 可用）与 no_expiry 的包；
  - 合并多个账号、按发放时间倒序、认不出的时间不炸也不插队；
  - 摘要（笔数 / 合计 / 剩余 / 已用 / 账号数）与快照时刻；
  - 只读：账号的 fetch_credits 一次都不许被调到；
  - 脏数据（非 dict 的包、缺 credits、空池）不炸也不多出一行。

    python tests/_test_credit_grants.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _isolated_dirs import isolated_data_dirs  # noqa: E402  (its own data root)

_TMP = isolated_data_dirs("wb-credit-grants-")

import wb_proxy as P  # noqa: E402

PASS = FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [PASS] " + label)
    else:
        FAIL += 1
        print("  [FAIL] " + label + ("  " + str(extra) if extra else ""))


class FakeAccount:
    """A pool member carrying a credit snapshot; the upstream is off limits."""

    def __init__(self, uid, nickname, realm, packages, updated_at=None,
                 credits=True):
        self.uid, self.nickname, self.realm = uid, nickname, realm
        self.credits = {"packages": packages} if credits else None
        if updated_at:
            self.credits["updated_at"] = updated_at

    def fetch_credits(self):
        raise AssertionError("credit_grants must not touch the upstream")


class FakePool:
    def __init__(self, accounts):
        self.accounts = accounts


def pkg(name, size, remain, create, expire="", **over):
    out = {"name": name, "size": size, "remain": remain, "used": size - remain,
           "create_time": create, "expire_time": expire}
    out.update(over)
    return out


NOW = P._parse_stamp_epoch("2026-10-10 14:00:00")

ALPHA = [
    pkg("Bonus Pack", 30, 12.54, "2026-10-10 00:42:45", "2026-11-10 00:42:44",
        in_usage=True, days_left=30.5),
    pkg("Bonus Pack", 30, 30, "2026-10-09 00:35:57", "2026-11-09 00:35:56"),
    pkg("Bonus Pack", 30, 0, "2026-10-08 00:37:41", "2026-11-08 00:37:40"),
    "not-a-package",
]
BRAVO = [
    pkg("Free Plan Subscription", 100, 100, "2026-09-18 21:27:53",
        "2034-12-18 21:27:52", no_expiry=True),
    pkg("Campaign Pack", 30, 5, "2026-09-20 03:00:00", "2026-10-01 03:00:00"),
    pkg("Flagged Expired", 50, 50, "2026-09-21 03:00:00", "2026-12-01 03:00:00",
        is_expired=True),
    pkg("Unknown Stamp", 10, 10, "n/a"),
]

print("[1] 合并两个账号的包，按发放时间倒序")

pool = FakePool([
    FakeAccount("uid-alpha", "meyadi", "intl", ALPHA, updated_at=NOW - 3600),
    FakeAccount("uid-bravo", "hades", "cn", BRAVO, updated_at=NOW - 7200),
    FakeAccount("uid-empty", "empty", "intl", [], credits=False),
])
_saved_pool = P.POOL
try:
    P.POOL = pool
    data = P.credit_grants(now=NOW)
finally:
    P.POOL = _saved_pool

rows = data["rows"]
check("非 dict 的包被跳过", len(rows) == 7, [r["name"] for r in rows])
check("按发放时间倒序（认不出时间的排最后）",
      [r["name"] for r in rows] ==
      ["Bonus Pack", "Bonus Pack", "Bonus Pack", "Flagged Expired",
       "Campaign Pack", "Free Plan Subscription", "Unknown Stamp"],
      [r["name"] for r in rows])
check("昵称与区域跟着账号走",
      rows[0]["nickname"] == "meyadi" and rows[0]["realm"] == "intl"
      and rows[3]["nickname"] == "hades" and rows[3]["realm"] == "cn")
check("没有积分快照的账号不产出行（也不报错）",
      all(r["uid"] != "uid-empty" for r in rows))

print()
print("[2] 状态判定：过期 > 用完 > 在扣减 > 可用")

by_name = {}
for r in rows:
    by_name.setdefault(r["name"], []).append(r)
check("in_usage 的包是 active", by_name["Bonus Pack"][0]["status"] == "active",
      by_name["Bonus Pack"][0])
check("有剩余、未过期的包是 available",
      by_name["Bonus Pack"][1]["status"] == "available", by_name["Bonus Pack"][1])
check("剩余为 0 的包是 used_up",
      by_name["Bonus Pack"][2]["status"] == "used_up", by_name["Bonus Pack"][2])
check("到期时刻已过的是 expired",
      by_name["Campaign Pack"][0]["status"] == "expired",
      by_name["Campaign Pack"][0])
check("上游标了 is_expired 的也是 expired（到期时刻还没到也算）",
      by_name["Flagged Expired"][0]["status"] == "expired",
      by_name["Flagged Expired"][0])
check("no_expiry 的包照常 available",
      by_name["Free Plan Subscription"][0]["status"] == "available"
      and by_name["Free Plan Subscription"][0]["no_expiry"] is True,
      by_name["Free Plan Subscription"][0])
check("认不出的发放时间不炸：create_at 为空但行还在",
      by_name["Unknown Stamp"][0]["create_at"] is None,
      by_name["Unknown Stamp"][0])
check("days_left 原样带出（有就给）",
      by_name["Bonus Pack"][0]["days_left"] == 30.5, by_name["Bonus Pack"][0])

print()
print("[3] 摘要与快照时刻")

summary = data["summary"]
check("笔数 = 行数", summary["count"] == 7, summary)
check("合计面额", summary["size"] == 280, summary)
check("合计剩余", summary["remain"] == round(12.54 + 30 + 0 + 100 + 5 + 50 + 10, 2),
      summary)
check("账号数按去重算", summary["accounts"] == 2, summary)
check("快照时刻取最新的 updated_at", data["fetched_at"] == NOW - 3600, data)
check("快照时刻同时给 ISO",
      data["fetched_iso"] == P.time.strftime("%Y-%m-%d %H:%M:%S",
                                            P.time.localtime(NOW - 3600)),
      data["fetched_iso"])

print()
print("[4] 空池与脏输入")

try:
    P.POOL = FakePool([])
    empty = P.credit_grants(now=NOW)
finally:
    P.POOL = _saved_pool
check("空池：没有行，摘要归零",
      empty["rows"] == [] and empty["summary"]["count"] == 0
      and empty["summary"]["size"] == 0 and empty["fetched_at"] is None, empty)

check("认不出的时间戳返回 None，不抛异常",
      P._parse_stamp_epoch("n/a") is None and P._parse_stamp_epoch("") is None
      and P._parse_stamp_epoch(None) is None)
check("正常时间戳认得出来",
      P._parse_stamp_epoch("2026-10-10 00:42:45") ==
      P.time.mktime(P.time.strptime("2026-10-10 00:42:45", "%Y-%m-%d %H:%M:%S")))
check("剩余是脏值时按 0 处理",
      P._grant_status({"remain": "oops"}, NOW) == P.GRANT_STATUS_USED_UP)

print()
print("[5] 处理函数：200 + 同一份载荷")


class FakeHandler:
    def __init__(self):
        self.response = None

    def _authorized(self):
        return True

    def _json(self, code, obj):
        self.response = (code, obj)
        return (code, obj)


handler = FakeHandler()
try:
    P.POOL = pool
    code, body = P.Handler._get_account_credits_grants(handler)
finally:
    P.POOL = _saved_pool
check("返回 200", code == 200, code)
check("载荷带 ok / rows / summary / 快照时刻",
      body.get("ok") is True and isinstance(body.get("rows"), list)
      and body["summary"]["count"] == len(body["rows"])
      and body.get("fetched_iso"), body)

print()
print("PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
