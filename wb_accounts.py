"""Multi-account pool and OAuth login for the WorkBuddy international proxy.

Accounts are stored as one plain JSON file per account under ./accounts/.
Tokens are deliberately NOT encrypted - same as the desktop app - so that any
local tool can read them. Do not put this directory on a shared drive.

OAuth flow (verified against www.workbuddy.ai):

    POST /v2/plugin/auth/state?platform=CLI
        -> { state, authUrl }
    user opens authUrl in a browser and signs in
    GET  /v2/plugin/auth/token?state=<state>
        -> code 11217 while pending, code 0 with the token bundle when done
    GET  /v2/plugin/login/account?state=<state>   (Bearer)
        -> account profile (uid / nickname)
    POST /v2/auth/token/refresh                   (X-Refresh-Token)
        -> fresh access token
"""

import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid

UPSTREAM = "https://www.workbuddy.ai"
#: How the official international client identifies itself upstream.
#:
#: Not guessed - read out of the shipped WorkBuddy AI client:
#:   packages/product/src/common/client-info/user-agent-http-interceptor.ts
#:       buildUserAgent() -> "{platform}/{pv} {productName}/{prv} {ext}"
#:   packages/workbuddy-server/src/runtime/client-info-env.ts
#:       WORKBUDDY_PLATFORM = "WorkBuddy"
#:       CLIENT_INFO_USER_AGENT_EXTENSION = "CLI/<cli version>"
#:   cli/product.json          productName = "WorkBuddy AI"
#:   cli/package.json          version     = the CLI version
#:
#: The CN build ships a different brand ("CodeBuddy") and version line, so a
#: CN-flavoured UA on an intl credential is an avoidable mismatch.
DEFAULT_UA_PLATFORM = "WorkBuddy"
DEFAULT_UA_PRODUCT = "WorkBuddy AI"
DEFAULT_UA_VERSION = "5.5.2"


def discover_client_version():
    """Best-effort version of the installed WorkBuddy AI client."""
    home = os.path.expanduser("~")
    for path, key in ((os.path.join(home, ".workbuddy-ai", "last-launch.json"), "version"),
                      (os.path.join(home, ".workbuddy-ai", "cache",
                                    "acc-product-config-v3.json"), "genieVersion")):
        try:
            with open(path, encoding="utf-8") as fh:
                value = str(json.load(fh).get(key) or "").strip()
            if value:
                return value
        except Exception:
            continue
    return DEFAULT_UA_VERSION


def build_user_agent(version=None, platform=None, product=None, extension=None):
    """UA in the shape the official intl client emits."""
    ver = (version or discover_client_version() or DEFAULT_UA_VERSION).strip()
    plat = (platform or DEFAULT_UA_PLATFORM).strip()
    prod = (product or DEFAULT_UA_PRODUCT).strip()
    parts = []
    if plat:
        parts.append("%s/%s" % (plat, ver))
    if prod:
        parts.append("%s/%s" % (prod, ver))
    ext = extension if extension is not None else ("CLI/%s" % ver)
    if ext:
        parts.append(ext)
    return " ".join(parts)


#: Resolved once at import; main() can override it with --user-agent.
USER_AGENT = build_user_agent()

AUTH_STATE_PATH = "/v2/plugin/auth/state"
AUTH_TOKEN_PATH = "/v2/plugin/auth/token"
LOGIN_ACCOUNT_PATH = "/v2/plugin/login/account"
REFRESH_PATH = "/v2/plugin/auth/token/refresh"

LOGIN_PENDING = 11217
LOGIN_TTL_SECONDS = 600

_HEADER_BASE = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": USER_AGENT,
    "Origin": UPSTREAM,
    "Referer": UPSTREAM + "/",
    "X-Product": "SaaS",
}


def _request(url, method="GET", token=None, body=None, extra=None, timeout=30):
    headers = dict(_HEADER_BASE)
    if token:
        headers["Authorization"] = "Bearer " + token
    if extra:
        headers.update(extra)
    data = body if body is not None else (b"{}" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def _jwt_claims(token):
    try:
        segment = str(token).split(".")[1]
        segment += "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment))
    except Exception:
        return {}


def jwt_exp(token):
    try:
        return int(_jwt_claims(token).get("exp") or 0)
    except Exception:
        return 0


def jwt_uid(token):
    return str(_jwt_claims(token).get("sub") or "")


def jwt_issuer(token):
    return str(_jwt_claims(token).get("iss") or "")


def normalize_epoch(value):
    """Accept seconds or milliseconds and always return seconds."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number > 1e11:          # milliseconds (e.g. 1820646290252)
        number /= 1000.0
    return int(number)


def is_intl_token(token):
    return "workbuddy.ai" in jwt_issuer(token).lower()


class Account(object):
    """A single credential plus its bookkeeping."""

    def __init__(self, data, path=None):
        data = data or {}
        self.path = path
        token = str(data.get("accessToken") or "")
        self.uid = str(data.get("uid") or jwt_uid(token))
        self.nickname = str(data.get("nickname") or "")
        self.domain = str(data.get("domain") or "www.workbuddy.ai")
        self.platform = str(data.get("platform") or "CLI")
        self.access_token = token
        self.refresh_token = str(data.get("refreshToken") or "")
        self.expires_at = normalize_epoch(data.get("expiresAt")) or jwt_exp(token)
        self.added_at = data.get("addedAt") or time.time()
        self.source = str(data.get("source") or "oauth")
        self.enabled = data.get("enabled", True)
        self.last_error = str(data.get("lastError") or "")
        self.cooldown_until = float(data.get("cooldownUntil") or 0)
        self.credits = data.get("credits") or None

    # ------------------------------------------------------------------ state
    def to_dict(self):
        return {
            "uid": self.uid,
            "nickname": self.nickname,
            "domain": self.domain,
            "platform": self.platform,
            "accessToken": self.access_token,
            "refreshToken": self.refresh_token,
            "expiresAt": self.expires_at,
            "addedAt": self.added_at,
            "source": self.source,
            "enabled": self.enabled,
            "lastError": self.last_error,
            "cooldownUntil": self.cooldown_until,
            "credits": self.credits,
        }

    def public(self):
        """Display view. The token value is never included."""
        exp = self.expires_at or jwt_exp(self.access_token)
        return {
            "uid": self.uid,
            "nickname": self.nickname or (self.uid[:8] if self.uid else "?"),
            "domain": self.domain,
            "platform": self.platform,
            "enabled": bool(self.enabled),
            "source": self.source,
            "expiresAt": exp,
            "expiresIn": _human_delta(exp - time.time()) if exp else None,
            "hasRefreshToken": bool(self.refresh_token),
            "lastError": self.last_error,
            "inCooldown": self.cooldown_until > time.time(),
            "cooldownFor": round(max(0.0, self.cooldown_until - time.time())) or None,
            "addedAt": self.added_at,
            "file": os.path.basename(self.path) if self.path else None,
            "credits": self.credits,
        }

    def save(self, directory):
        os.makedirs(directory, exist_ok=True)
        name = (self.uid or uuid.uuid4().hex) + ".json"
        path = os.path.join(directory, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        self.path = path
        return path

    def delete(self):
        if self.path and os.path.exists(self.path):
            os.remove(self.path)

    def ready(self):
        """Can this account serve a request right now?"""
        if not self.enabled or not self.access_token:
            return False
        if self.cooldown_until > time.time():
            return False
        exp = self.expires_at or jwt_exp(self.access_token)
        if not exp:
            return True                      # no expiry info: assume usable
        remaining = exp - time.time()
        if remaining > 120:
            return True                      # comfortable margin
        if remaining > 0:
            self.refresh()                   # renew opportunistically
            return True                      # valid right now either way
        return self.refresh()                # expired: must renew

    def fetch_credits(self):
        """Query real-time credits/quota from /v2/billing/meter/get-user-resource."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        body = {
            "PageNumber": 1,
            "PageSize": 100,
            "ProductCode": "p_tcaca",
            "Status": [0, 3],
            "PackageEndTimeRangeBegin": now,
            "PackageEndTimeRangeEnd": "2036-01-01 00:00:00",
        }
        url = UPSTREAM + "/v2/billing/meter/get-user-resource"
        headers = dict(_HEADER_BASE)
        headers["Authorization"] = "Bearer " + self.access_token
        headers["X-User-Id"] = self.uid
        headers["X-Domain"] = self.domain
        headers["X-Product"] = "SaaS"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        data = res.get("data", {}).get("Response", {}).get("Data", {})
        accounts = data.get("Accounts") or []
        tot_remain, tot_used, tot_size = 0, 0, 0
        packages = []
        for a in accounts:
            pkg_name = a.get("PackageName") or "Package"
            if a.get("CycleCapacitySize", 0) > 0:
                remain = a.get("CycleCapacityRemain", 0)
                size = a.get("CycleCapacitySize", 0)
                used = max(0, size - remain)
                if a.get("CycleCapacityUsed", 0) > used:
                    used = a["CycleCapacityUsed"]
                    remain = max(0, size - used)
            else:
                remain = a.get("CapacityRemain", 0)
                used = a.get("CapacityUsed", 0)
                size = a.get("CapacitySize", 0)
            tot_remain += remain
            tot_used += used
            tot_size += size
            packages.append({"name": pkg_name, "remain": remain, "used": used, "size": size})

        self.credits = {
            "remain": tot_remain,
            "used": tot_used,
            "size": tot_size,
            "packages": packages,
            "updated_at": time.time(),
            "updated_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self.path and os.path.exists(os.path.dirname(self.path)):
            self.save(os.path.dirname(self.path))
        return {"ok": True, "credits": self.credits}

    def refresh(self):
        if not self.refresh_token:
            self.last_error = "no refresh token; sign in again"
            return False
        extra = {
            "X-Refresh-Token": self.refresh_token,
            "X-Auth-Refresh-Source": "plugin",
            "X-User-Id": self.uid,
            "X-Domain": self.domain,
        }
        try:
            payload = _request(UPSTREAM + REFRESH_PATH, method="POST", extra=extra)
        except Exception as exc:
            self.last_error = "refresh failed: %s" % exc
            return False
        data = (payload.get("data") or {})
        data = data.get("data") or data
        token = data.get("accessToken")
        if not token:
            self.last_error = "refresh returned no token (%s)" % payload.get("msg")
            return False
        self.access_token = token
        self.refresh_token = data.get("refreshToken") or self.refresh_token
        self.expires_at = jwt_exp(token) or self.expires_at
        self.last_error = ""
        self.cooldown_until = 0
        return True

    def headers(self):
        headers = dict(_HEADER_BASE)
        headers["Authorization"] = "Bearer " + self.access_token
        headers["X-User-Id"] = self.uid
        headers["X-No-Enterprise-Id"] = "1"
        headers["X-Domain"] = self.domain
        return headers

    def note_error(self, message, cooldown=90):
        self.last_error = str(message)[:200]
        self.cooldown_until = time.time() + cooldown

    def clear_error(self):
        if self.last_error or self.cooldown_until:
            self.last_error = ""
            self.cooldown_until = 0


def _human_delta(seconds):
    if seconds is None:
        return None
    if seconds <= 0:
        return "expired"
    days = seconds / 86400.0
    if days >= 1:
        return "%.0f days" % days
    hours = seconds / 3600.0
    if hours >= 1:
        return "%.1f hours" % hours
    return "%d min" % int(seconds / 60)


class SessionAffinity(object):
    """Binds conversation/session IDs to specific accounts with TTL."""
    def __init__(self, ttl=7200, max_entries=5000):
        self.ttl = ttl
        self.max_entries = max_entries
        self.bindings = {}  # session_key -> (uid, expire_at)
        self._lock = threading.Lock()

    def get(self, key):
        if not key:
            return None
        with self._lock:
            entry = self.bindings.get(key)
            if not entry:
                return None
            uid, exp = entry
            if time.time() > exp:
                self.bindings.pop(key, None)
                return None
            self.bindings[key] = (uid, time.time() + self.ttl)
            return uid

    def bind(self, key, uid):
        if not key or not uid:
            return
        with self._lock:
            if len(self.bindings) >= self.max_entries:
                now = time.time()
                self.bindings = {k: v for k, v in self.bindings.items() if v[1] > now}
            self.bindings[key] = (uid, time.time() + self.ttl)

    def unbind(self, key):
        if not key:
            return
        with self._lock:
            self.bindings.pop(key, None)


class AccountPool(object):
    """Round-robin pool over the accounts on disk."""

    def __init__(self, directory, log=None):
        self.dir = directory
        self.log = log or (lambda msg: None)
        self.accounts = []
        self.logins = {}
        self._lock = threading.RLock()
        self._cursor = 0
        self.affinity = SessionAffinity()

    # ------------------------------------------------------------- lifecycle
    def load(self):
        with self._lock:
            self.accounts = []
            if not os.path.isdir(self.dir):
                return self.accounts
            for name in sorted(os.listdir(self.dir)):
                if not name.endswith(".json"):
                    continue
                path = os.path.join(self.dir, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        account = Account(json.load(fh), path)
                except Exception as exc:
                    self.log("account %s unreadable: %s" % (name, exc))
                    continue
                if account.uid:
                    self.accounts.append(account)
            return self.accounts

    def list_public(self):
        with self._lock:
            return [a.public() for a in self.accounts]

    def get(self, uid):
        with self._lock:
            for account in self.accounts:
                if account.uid == uid:
                    return account
        return None

    def add(self, account):
        with self._lock:
            existing = self.get(account.uid)
            if existing is not None:
                account.added_at = existing.added_at
                account.path = existing.path
                self.accounts[self.accounts.index(existing)] = account
            else:
                self.accounts.append(account)
            account.save(self.dir)
        return account

    def remove(self, uid):
        with self._lock:
            account = self.get(uid)
            if account is None:
                return False
            account.delete()
            self.accounts.remove(account)
            return True

    def set_enabled(self, uid, enabled):
        account = self.get(uid)
        if account is None:
            return None
        account.enabled = bool(enabled)
        if enabled:
            account.clear_error()
        account.save(self.dir)
        return account.public()

    def set_all_enabled(self, enabled):
        with self._lock:
            for account in self.accounts:
                account.enabled = bool(enabled)
                if enabled:
                    account.clear_error()
                account.save(self.dir)

    def count_ready(self):
        with self._lock:
            snapshot = list(self.accounts)
        return sum(1 for a in snapshot if a.enabled and a.access_token)

    # ---------------------------------------------------------------- picking
    def pick_for_session(self, session_key=None, exclude=None):
        """Pick an account respecting session affinity when possible."""
        exclude = exclude or set()
        if session_key:
            bound_uid = self.affinity.get(session_key)
            if bound_uid and bound_uid not in exclude:
                account = self.get(bound_uid)
                if account and account.ready():
                    return account
                self.affinity.unbind(session_key)

        account = self.pick(exclude=exclude)
        if account and session_key:
            self.affinity.bind(session_key, account.uid)
        return account

    def pick(self, exclude=None):
        """Next usable account, round-robin. exclude is a set of uids."""
        exclude = exclude or set()
        with self._lock:
            snapshot = list(self.accounts)
            start = self._cursor
        total = len(snapshot)
        for offset in range(total):
            index = (start + offset) % total
            account = snapshot[index]
            if account.uid in exclude:
                continue
            if account.ready():
                with self._lock:
                    self._cursor = (index + 1) % total
                return account
        return None

    def representative(self):
        """An account used for display when nothing is being routed."""
        with self._lock:
            for account in self.accounts:
                if account.access_token:
                    return account
            return self.accounts[0] if self.accounts else None

    # ------------------------------------------------------------------ oauth
    def start_login(self, platform="CLI"):
        url = "%s%s?platform=%s" % (UPSTREAM, AUTH_STATE_PATH,
                                    urllib.parse.quote(str(platform)))
        payload = _request(url, method="POST")
        data = payload.get("data") or {}
        state = data.get("state")
        auth_url = data.get("authUrl")
        if not state or not auth_url:
            raise RuntimeError("auth/state returned no state/authUrl: %s" % payload)
        with self._lock:
            self.logins[state] = {"created": time.time(), "platform": platform}
        return {"state": state, "authUrl": auth_url, "platform": platform}

    def poll_login(self, state):
        state = str(state or "").strip()
        with self._lock:
            info = self.logins.get(state)
        if not info:
            return {"status": "unknown",
                    "message": "state not recognised - start the login again"}
        if time.time() - info["created"] > LOGIN_TTL_SECONDS:
            with self._lock:
                self.logins.pop(state, None)
            return {"status": "expired",
                    "message": "login window expired - start again"}

        try:
            payload = _request("%s%s?state=%s" % (UPSTREAM, AUTH_TOKEN_PATH,
                                                  urllib.parse.quote(state)))
        except Exception as exc:
            return {"status": "pending", "message": "poll error: %s" % exc}

        code = payload.get("code")
        if code == LOGIN_PENDING:
            return {"status": "pending",
                    "message": payload.get("msg") or "waiting for browser login"}
        if code != 0:
            return {"status": "error",
                    "message": "code=%s msg=%s" % (code, payload.get("msg"))}

        data = payload.get("data") or {}
        token = data.get("accessToken")
        if not token:
            return {"status": "pending", "message": "waiting for token"}
        if not is_intl_token(token):
            return {"status": "error",
                    "message": "this account belongs to another realm, not www.workbuddy.ai"}

        uid = jwt_uid(token)
        nickname = ""
        try:
            profile = _request("%s%s?state=%s" % (UPSTREAM, LOGIN_ACCOUNT_PATH,
                                                  urllib.parse.quote(state)), token=token)
            profile_data = profile.get("data") or {}
            nickname = str(profile_data.get("nickname") or "")
        except Exception:
            pass

        account = Account({
            "uid": uid,
            "nickname": nickname or uid[:8],
            "domain": data.get("domain") or "www.workbuddy.ai",
            "platform": info["platform"],
            "accessToken": token,
            "refreshToken": data.get("refreshToken") or "",
            "expiresAt": normalize_epoch(data.get("expiresAt")) or jwt_exp(token),
            "source": "oauth",
            "enabled": True,
        })
        self.add(account)
        with self._lock:
            self.logins.pop(state, None)
        return {"status": "ok", "account": account.public()}

    def cancel_login(self, state):
        with self._lock:
            return self.logins.pop(state, None) is not None

    # ----------------------------------------------------------------- import
    def import_desktop_credential(self, path, source="desktop-app"):
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        auth = blob.get("auth") or {}
        profile = blob.get("account") or {}
        token = str(auth.get("accessToken") or "")
        if not token:
            raise RuntimeError("no accessToken in %s" % path)
        if not is_intl_token(token):
            raise RuntimeError("credential at %s is not the intl realm" % path)
        account = Account({
            "uid": profile.get("uid") or jwt_uid(token),
            "nickname": profile.get("nickname") or "",
            "domain": auth.get("domain") or "www.workbuddy.ai",
            "platform": "CLI",
            "accessToken": token,
            "refreshToken": auth.get("refreshToken") or "",
            "expiresAt": normalize_epoch(auth.get("expiresAt")) or jwt_exp(token),
            "source": source,
            "enabled": True,
        })
        return self.add(account)


def desktop_credential_candidates():
    """Where the desktop app keeps its intl session, newest first."""
    base = desktop_auth_dir()
    out = []
    if os.path.isdir(base):
        for name in os.listdir(base):
            if name.endswith(".info"):
                path = os.path.join(base, name)
                out.append((os.path.getmtime(path), path))
    out.sort(reverse=True)
    return [p for _, p in out]


def desktop_auth_dir():
    """Directory the desktop app stores its sessions in."""
    local = os.environ.get("LOCALAPPDATA", "")
    base = os.path.join(local, "CodeBuddyExtension", "Data", "Public", "auth")
    return base
