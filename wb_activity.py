"""wb_activity.py —— 账号每日活动的结构化历史（issue #34，父 issue #30）

国内版签到与国际版每日活跃，过去只留在调度器的滚动日志里：重启即散，而且和
Token 保活、猫猫旅行、成长任务混在同一条流里，回答不了「这个账号昨天到底签成
了没有」。这里落一份独立的结构化历史，一行一次**真实尝试**，不是每轮巡检。

写进去的是运维元数据，不是凭证：时间 / uid / 昵称 / 区域 / 任务 / 触发来源 /
结果 / 一句截断并脱敏过的说明。token、cookie、API key、授权头、原始请求体既不
落盘，也不会出现在读取结果里。

路径沿用 wb_pricing 的做法：wb_proxy 启动时用 set_data_dir() 把它指到自己的
数据目录。`--usage-dir` 会改这个目录，所以路径不能在 import 时定死。
"""
import datetime
import json
import os
import re
import sys
import threading
import time

HISTORY_NAME = "activity_history.jsonl"

TASK_CHECKIN = "checkin"
TASK_DAILY_CHAT = "daily_chat"
TASKS = (TASK_CHECKIN, TASK_DAILY_CHAT)

# 触发来源只用于面板上的来源标注；认不出来的值归一成 unknown —— 记历史绝不能
# 让签到本身失败，也不该因为一个标签写错就丢掉一次真实尝试。
TRIGGERS = ("scheduler", "manual", "account_add", "account_import", "unknown")

RESULTS = ("ok", "failed")
RESULT_ALIASES = {"ok": "ok", "success": "ok", "succeeded": "ok",
                  "failed": "failed", "fail": "failed", "failure": "failed"}

DEFAULT_RANGE = "7d"
RANGE_DAYS = {"today": 1, "1d": 1, "7d": 7, "30d": 30, "90d": 90, "all": None}

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# 保留策略：90 天与 5000 行取交集。整理不跟着每次追加做 —— 只有文件超过
# COMPACT_TRIGGER_BYTES 才整理一次。这个阈值特意高于「上限行数本身的大小」
# （约 1.2 MB），所以整理一定会把文件缩回去，下一次整理要再过几千条才会到，
# 不会在阈值边缘变成每条都重写一遍。
MAX_RECORDS = 5000
MAX_AGE_DAYS = 90
COMPACT_TRIGGER_BYTES = 2000000

# 上游原文的截断长度：历史表一行只该是一句人能读的原因。
MAX_MESSAGE = 200

_lock = threading.Lock()
_data_dir_override = None


def set_data_dir(path):
    """wb_proxy 把它指到自己的数据目录，两边看同一份文件。"""
    global _data_dir_override
    with _lock:
        _data_dir_override = path


def data_dir():
    """历史文件所在目录：wb_proxy 指定的优先，其次环境变量，最后仓库内默认。"""
    if _data_dir_override:
        return _data_dir_override
    env = os.environ.get("WB_PROXY_USAGE_DIR")
    return env or os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage")


def history_path():
    return os.path.join(data_dir(), HISTORY_NAME)


def _gateway():
    """真正在跑的那个网关模块（容器里是 `python wb_proxy.py`，即 __main__）。"""
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "log"):
        return main
    return sys.modules.get("wb_proxy")


def _log(message):
    """把写失败反映到面板日志里；记录本身不依赖这一步。"""
    try:
        module = _gateway()
        if module is not None:
            module.log("[活动记录] %s" % message, level="WARN")
    except Exception:
        pass


# 上游的错误文本是自由文本，401/403 的正文里回显授权头是常见现象，所以写进历史
# 前先按已知的凭证形态打码。这是「截断 + 已知形态打码」，不是通用清洗：能落盘的
# 只该是一句人能读的原因。
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:access[_-]?token|refresh[_-]?token|api[_-]?key|apikey|"
               r"authorization|cookie|set-cookie|password|secret|token)\b"
               r"\s*[:=]\s*\S+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
)
_REDACTED = "[redacted]"


def safe_message(text):
    """把上游原文压成一行安全的短说明。"""
    line = " ".join(str(text or "").split())
    for pattern in _SECRET_PATTERNS:
        line = pattern.sub(_REDACTED, line)
    return line[:MAX_MESSAGE]


def _timestamp():
    """本地时间带偏移量：面板按本地时间显示，读取端不必再猜是哪个时区。"""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_ts(value):
    try:
        return datetime.datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


def record(uid, nickname, realm, task, trigger, ok, message, usage_dir=None):
    """追加一次尝试。返回写入的那一行；写不进去时返回 None。

    绝不抛异常：磁盘满、文件被占用都不该把一次成功的签到变成失败。文件超过
    COMPACT_TRIGGER_BYTES 时顺手整理一次，整理失败的原始文件保持不变。
    """
    row = {
        "ts": _timestamp(),
        "uid": str(uid or ""),
        "nickname": str(nickname or ""),
        "realm": realm if realm in ("cn", "intl") else "",
        "task": task,
        "trigger": trigger if trigger in TRIGGERS else "unknown",
        "ok": bool(ok),
        "message": safe_message(message),
    }
    path = os.path.join(usage_dir, HISTORY_NAME) if usage_dir else history_path()
    try:
        with _lock:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if os.path.getsize(path) > COMPACT_TRIGGER_BYTES:
                _compact_locked(path)
    except Exception as exc:
        _log("写入失败: %s" % exc)
        return None
    return row


def record_attempt(account, task, trigger, result):
    """把一次账号尝试的结果记成一行；trigger 为 None 表示这一步不单独记。

    trigger=None 是给嵌套调用用的：daily_chat() 内部还会跑一次网页通道，那一步
    属于同一次尝试，由外层记一次就够，不该在历史里多出一行。
    """
    if trigger is None:
        return None
    result = result if isinstance(result, dict) else {}
    ok = bool(result.get("ok"))
    message = result.get("msg") or result.get("error") or ("成功" if ok else "失败")
    return record(uid=getattr(account, "uid", ""),
                  nickname=getattr(account, "nickname", ""),
                  realm=getattr(account, "realm", ""),
                  task=task, trigger=trigger, ok=ok, message=message)


def _read_rows(path):
    """按写入顺序读出全部记录；坏行跳过，不让一条截断的行毁掉整个文件。"""
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except FileNotFoundError:
        return []
    except OSError as exc:
        _log("读取失败: %s" % exc)
    return rows


def load(usage_dir=None):
    path = os.path.join(usage_dir, HISTORY_NAME) if usage_dir else history_path()
    return _read_rows(path)


def range_days(value):
    """range 参数对应的天数；None 表示不设下限。认不出来就抛 ValueError。"""
    key = str(value or DEFAULT_RANGE).strip().lower()
    if key not in RANGE_DAYS:
        raise ValueError("range must be one of: " + ", ".join(sorted(RANGE_DAYS)))
    return RANGE_DAYS[key]


def query(range_key=None, uid=None, task=None, result=None, limit=None,
          usage_dir=None):
    """读取历史（最新在前）。筛选在服务端做完，limit 有默认值与上限。

    认不出来的筛选值抛 ValueError，由路由翻成 400：静默忽略一个写错的筛选条件
    会让调用方以为「这几天没有失败」，而实际上它把全部结果都拿回去了。
    """
    key = str(range_key or DEFAULT_RANGE).strip().lower()
    days = range_days(key)
    task = (task or "").strip()
    if task and task not in TASKS:
        raise ValueError("task must be one of: " + ", ".join(TASKS))
    result = (result or "").strip().lower()
    if result and result not in RESULT_ALIASES:
        raise ValueError("result must be one of: " + ", ".join(RESULTS))
    result = RESULT_ALIASES.get(result, "")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(MAX_LIMIT, limit))

    uid = (uid or "").strip()
    cutoff = None if days is None else time.time() - days * 86400
    matched = []
    # 文件是追加写的，追加序就是时间序，倒过来即最新在前。
    for row in reversed(load(usage_dir=usage_dir)):
        if uid and str(row.get("uid") or "") != uid:
            continue
        if task and row.get("task") != task:
            continue
        if result and bool(row.get("ok")) != (result == "ok"):
            continue
        if cutoff is not None:
            ts = _parse_ts(row.get("ts"))
            if ts is not None and ts < cutoff:
                continue
        matched.append(row)
    return {"rows": matched[:limit], "total": len(matched), "limit": limit,
            "range": key,
            "filters": {"uid": uid, "task": task, "result": result}}


def compact(usage_dir=None, max_records=None, max_age_days=None):
    """按保留策略整理历史，返回 (保留行数, 丢弃行数)。"""
    path = os.path.join(usage_dir, HISTORY_NAME) if usage_dir else history_path()
    with _lock:
        return _compact_locked(path, max_records=max_records,
                               max_age_days=max_age_days)


def _compact_locked(path, max_records=None, max_age_days=None):
    """整理实现；调用方必须已经持有 _lock。

    先写临时文件再 os.replace，所以任何时刻读到的都是一份完整文件，整理中途
    失败也不会碰原文件。
    """
    max_records = MAX_RECORDS if max_records is None else max_records
    max_age_days = MAX_AGE_DAYS if max_age_days is None else max_age_days
    rows = _read_rows(path)
    if not rows:
        return (0, 0)
    cutoff = time.time() - max_age_days * 86400
    keep = []
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        # 时间读不出来的行不按「过期」丢：那是一次无声的数据损失，宁可交给记录
        # 数上限去管它。
        if ts is not None and ts < cutoff:
            continue
        keep.append(row)
    if max_records > 0 and len(keep) > max_records:
        keep = keep[-max_records:]
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for row in keep:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except Exception as exc:
        _log("整理失败: %s" % exc)
        return (len(rows), 0)
    return (len(keep), len(rows) - len(keep))
