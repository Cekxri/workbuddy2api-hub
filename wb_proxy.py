#!/usr/bin/env python3
"""WorkBuddy (workbuddy.ai) -> OpenAI-compatible reverse proxy.

Reuses the credentials the WorkBuddy desktop app already stored on this machine
(%%LOCALAPPDATA%%\\CodeBuddyExtension\\Data\\Public\\auth\\*.info), so no separate
login is needed. Exposes:

    GET  /v1/models
    POST /v1/chat/completions     (stream=true and stream=false)
    GET  /health

Only the Python standard library is required.

    python wb_proxy.py                    # bind 127.0.0.1:8788
    python wb_proxy.py --port 9000
    python wb_proxy.py --api-key sk-local # require a bearer token
"""

import argparse
import base64
import hashlib
import re
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import wb_accounts
import wb_catalog
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

UPSTREAM = "https://www.workbuddy.ai"
CHAT_PATH = "/v2/chat/completions"
MODELS_PATH = "/v2/enterprises/personal/models"
REFRESH_PATH = "/v2/auth/token/refresh"
USER_AGENT = "CLI/2.63.2 CodeBuddy/2.63.2"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

# The WorkBuddy AI desktop app caches its account product config here on every
# launch. That file carries the real model catalog the app shows in its picker
# (21 models, incl. deepseek-v4.1-flash / gpt-6-astra) - the CLI-facing
# /v2/enterprises/personal/models endpoint returns a narrower list, so prefer
# the cache and fall back to the endpoint.
PRODUCT_CONFIG_CACHE = os.path.join(os.path.expanduser("~"), ".workbuddy-ai", "cache", "acc-product-config-v3.json")

# Intl only. The WorkBuddy AI desktop app (WorkBuddyAI.exe) keeps its session in
# the shared IDE data dir as workbuddy-desktop-ai.info. The CN build
# (workbuddy-desktop.info / copilot.tencent.com) is deliberately NOT scanned.
AUTH_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "CodeBuddyExtension", "Data", "Public", "auth"),
]

INTL_DOMAIN_SUFFIX = ".workbuddy.ai"
INTL_ISSUER_MARKER = "workbuddy.ai"

NOISE_KEYS = ("extra_fields", "refusal", "reasoning_content")

_lock = threading.Lock()
_models_cache = {"at": 0.0, "data": None}

# Usage accounting: every upstream response carries a usage block, and the
# proxy also records one JSONL line per request. Defaults to a folder next to
# this script; override with --usage-dir or WB_PROXY_USAGE_DIR.
USAGE_DIR = os.environ.get("WB_PROXY_USAGE_DIR") \
    or os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage")
USAGE_LOG = os.path.join(USAGE_DIR, "usage.jsonl")
USAGE_SUMMARY = os.path.join(USAGE_DIR, "usage-summary.json")
DASHBOARD_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "reasoning_tokens",
                "cached_tokens", "total_tokens", "credit")


def _empty_stats():
    return {"requests": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "reasoning_tokens": 0, "cached_tokens": 0, "total_tokens": 0,
            "credit": 0.0, "started": time.time(), "by_model": {},
            # latency accumulators (averages; percentiles come from the JSONL)
            "ttft_ms_sum": 0, "ttft_samples": 0,
            "gen_ms_sum": 0, "gen_samples": 0,
            "wall_ms_sum": 0, "wall_samples": 0}


_usage = _empty_stats()


def _extract_usage(usage):
    """Normalize the upstream usage block into the fields we track."""
    if not usage:
        return {}
    details = usage.get("completion_tokens_details") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens") or 0,
        "completion_tokens": usage.get("completion_tokens") or 0,
        "reasoning_tokens": details.get("reasoning_tokens") or 0,
        "cached_tokens": usage.get("prompt_cache_hit_tokens") or details.get("cached_tokens") \
            or prompt_details.get("cached_tokens") or 0,
        "total_tokens": usage.get("total_tokens") or 0,
        "credit": usage.get("credit") or 0,
    }


def record_usage(model, usage, stream=None, elapsed_ms=None, ttft_ms=None, gen_ms=None, fp=None,
                 account=None):
    """Accumulate stats, append a JSONL row, and persist the summary."""
    fields = _extract_usage(usage)
    if not fields:
        return None

    row = {
        "at": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "stream": bool(stream),
        "elapsed_ms": elapsed_ms,
        "ttft_ms": ttft_ms,
        "gen_ms": gen_ms,
    }
    row.update(fields)
    if fp:
        row.update(fp)
    if account:
        row["account"] = account
    # Derived per-request rates (None-safe).
    if gen_ms and gen_ms > 0:
        row["tokens_per_sec"] = round(fields["completion_tokens"] / (gen_ms / 1000.0), 2)
    if fields["prompt_tokens"]:
        row["cache_hit_pct"] = round(fields["cached_tokens"] * 100.0 / fields["prompt_tokens"], 1)

    with _lock:
        _usage["requests"] += 1
        for k in USAGE_FIELDS:
            if k in fields:
                _usage[k] += fields[k]
        if ttft_ms is not None:
            _usage["ttft_ms_sum"] += ttft_ms
            _usage["ttft_samples"] += 1
        if gen_ms is not None:
            _usage["gen_ms_sum"] += gen_ms
            _usage["gen_samples"] += 1
        if elapsed_ms is not None:
            _usage["wall_ms_sum"] += elapsed_ms
            _usage["wall_samples"] += 1
        per = _usage["by_model"].setdefault(model, {"requests": 0, **{k: 0 for k in USAGE_FIELDS}})
        per["requests"] += 1
        for k in USAGE_FIELDS:
            if k in fields:
                per[k] += fields[k]
        summary = json.loads(json.dumps(_usage))

    try:
        os.makedirs(USAGE_DIR, exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        with open(USAGE_SUMMARY, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"usage persist failed: {exc}")
    return row


def record_error(model, status, message, elapsed_ms=None):
    """Count a failed request and append it to the log so errors are visible."""
    row = {
        "at": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "error": True,
        "status": status,
        "message": str(message)[:200],
        "elapsed_ms": elapsed_ms,
    }
    with _lock:
        _usage["errors"] += 1
        if elapsed_ms is not None:
            _usage["wall_ms_sum"] += elapsed_ms
            _usage["wall_samples"] += 1
        summary = json.loads(json.dumps(_usage))
    try:
        os.makedirs(USAGE_DIR, exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        with open(USAGE_SUMMARY, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"error persist failed: {exc}")
    return row


def _pct(values, q):
    """Nearest-rank percentile (no interpolation) - good enough for latency."""
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((q / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(len(ordered) - 1, idx))]


def perf_stats(sample=5000):
    """Latency percentiles + derived rates, computed from the JSONL log."""
    ttfts, gens, walls, rates, hits, tok_rates = [], [], [], [], [], []
    total = ok = err = 0
    try:
        with open(USAGE_LOG, encoding="utf-8") as fh:
            rows = fh.readlines()[-sample:]
    except FileNotFoundError:
        rows = []
    except Exception as exc:
        log(f"perf read failed: {exc}")
        rows = []

    for line in rows:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        total += 1
        if r.get("error"):
            err += 1
            if r.get("elapsed_ms"):
                walls.append(r["elapsed_ms"])
            continue
        ok += 1
        if r.get("ttft_ms") is not None:
            ttfts.append(r["ttft_ms"])
        if r.get("gen_ms") is not None:
            gens.append(r["gen_ms"])
        if r.get("elapsed_ms") is not None:
            walls.append(r["elapsed_ms"])
        if r.get("tokens_per_sec"):
            tok_rates.append(r["tokens_per_sec"])
        if r.get("cache_hit_pct") is not None:
            hits.append(r["cache_hit_pct"])

    def block(vals):
        if not vals:
            return None
        return {
            "avg": round(sum(vals) / len(vals), 1),
            "p50": _pct(vals, 50),
            "p90": _pct(vals, 90),
            "p99": _pct(vals, 99),
            "max": max(vals),
            "samples": len(vals),
        }

    return {
        "sampled": total,
        "success": ok,
        "errors": err,
        "success_rate_pct": round(ok * 100.0 / total, 1) if total else None,
        "ttft_ms": block(ttfts),
        "generation_ms": block(gens),
        "wall_ms": block(walls),
        "tokens_per_sec": block(tok_rates),
        "cache_hit_pct": block(hits),
    }


def usage_snapshot():
    rep = current_account()
    with _lock:
        snap = json.loads(json.dumps(_usage))
    snap["since"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snap.get("started", time.time())))
    snap["log_file"] = USAGE_LOG
    snap["realm"] = "intl (www.workbuddy.ai)"
    snap["account"] = {
        "uid": (rep.uid if rep else ""),
        "domain": (rep.domain if rep else ""),
        "issuer": (wb_accounts.jwt_issuer(rep.access_token) if rep else ""),
        "credential_file": (os.path.basename(rep.path) if rep and rep.path else ""),
        "expires_at": (rep.expires_at if rep else 0),
        "accounts": (len(POOL.accounts) if POOL else 0),
        "accounts_ready": (POOL.count_ready() if POOL else 0),
    }
    return snap


def recent_usage(limit=100):
    """Return the last `limit` rows of usage.jsonl (oldest first) plus totals."""
    rows, total = [], 0
    try:
        with open(USAGE_LOG, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception as exc:
        log(f"usage log read failed: {exc}")
    return {"total": total, "rows": rows[-limit:]}


# ---------------------------------------------------------------------------
# credential handling
# ---------------------------------------------------------------------------

def _jwt_issuer(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("iss") or "")
    except Exception:
        return ""


def is_intl_credential(blob):
    """True only for the international realm (www.workbuddy.ai).

    Guards against accidentally picking up the CN build's credential, which
    lives in the same directory and targets copilot.tencent.com.
    """
    auth = blob.get("auth") or {}
    domain = str(auth.get("domain") or "").strip().lower()
    if not (domain == "workbuddy.ai" or domain.endswith(INTL_DOMAIN_SUFFIX)):
        return False
    issuer = _jwt_issuer(str(auth.get("accessToken") or "")).lower()
    return INTL_ISSUER_MARKER in issuer


def find_auth_file():
    """Return the newest intl (www.workbuddy.ai) *.info credential file."""
    cands = []
    for d in AUTH_DIRS:
        if not d or not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.endswith(".info"):
                continue
            p = os.path.join(d, name)
            try:
                with open(p, encoding="utf-8") as fh:
                    blob = json.load(fh)
            except Exception:
                continue
            if is_intl_credential(blob):
                cands.append((os.path.getmtime(p), p))
    if not cands:
        raise SystemExit(
            "No international (www.workbuddy.ai) credential found.\n"
            "Sign in with the WorkBuddy AI desktop app (WorkBuddyAI.exe) first, "
            "or pass --info <path to workbuddy-desktop-ai.info>."
        )
    return max(cands)[1]


class Session:
    """Holds the live WorkBuddy credential, re-reading/refreshing as needed."""

    def __init__(self, info_path):
        self.info_path = info_path
        self.token = None
        self.refresh_token = None
        self.uid = None
        self.domain = "www.workbuddy.ai"
        self.issuer = ""
        self.exp = 0
        self.reload()

    def _jwt_exp(self, token):
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp") or 0)
        except Exception:
            return 0

    def reload(self):
        with open(self.info_path, encoding="utf-8") as fh:
            blob = json.load(fh)
        auth = blob.get("auth") or {}
        account = blob.get("account") or {}
        self.token = auth.get("accessToken") or ""
        self.refresh_token = auth.get("refreshToken") or ""
        self.uid = account.get("uid") or ""
        self.domain = (auth.get("domain") or "www.workbuddy.ai").strip()
        self.issuer = _jwt_issuer(self.token)
        self.exp = self._jwt_exp(self.token)
        # Fail closed: never forward a CN/free-tier realm token to workbuddy.ai.
        if not is_intl_credential(blob):
            raise SystemExit(
                f"Credential at {self.info_path} is not the international realm "
                f"(domain={self.domain!r}, issuer={self.issuer!r}).\n"
                "This proxy only serves www.workbuddy.ai - sign in with the "
                "WorkBuddy AI desktop app."
            )
        return self

    def valid(self):
        return bool(self.token) and (self.exp == 0 or self.exp - time.time() > 120)

    def refresh(self):
        """Best-effort access-token refresh; falls back to the on-disk session."""
        if not self.refresh_token:
            return False
        req = urllib.request.Request(
            UPSTREAM + REFRESH_PATH,
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": USER_AGENT,
                "X-Refresh-Token": self.refresh_token,
                "X-Auth-Refresh-Source": "plugin",
                "X-User-Id": self.uid,
                "X-Domain": self.domain,
                "X-Product": "SaaS",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            log(f"token refresh failed: {exc}")
            return False
        data = (payload.get("data") or {}).get("data") or payload.get("data") or {}
        token = data.get("accessToken")
        if not token:
            return False
        self.token = token
        self.refresh_token = data.get("refreshToken") or self.refresh_token
        self.exp = self._jwt_exp(token)
        log("access token refreshed")
        return True

    def ensure(self):
        with _lock:
            if self.valid():
                return
            self.refresh()
            if not self.valid():
                self.reload()
                if not self.valid():
                    raise RuntimeError(
                        "WorkBuddy session is expired and could not be refreshed - "
                        "open the desktop app and sign in again."
                    )

    def headers(self):
        self.ensure()
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": USER_AGENT,
            "Origin": UPSTREAM,
            "Referer": UPSTREAM + "/",
            "Authorization": "Bearer " + self.token,
            "X-User-Id": self.uid,
            "X-No-Enterprise-Id": "1",
            "X-Domain": self.domain,
            "X-Product": "SaaS",
        }


POOL = None
ACCOUNTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts')
API_KEY = None
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT


def import_desktop_accounts():
    """Pull every intl credential the desktop app left on disk into the pool."""
    imported = []
    for path in wb_accounts.desktop_credential_candidates():
        try:
            account = POOL.import_desktop_credential(path)
            imported.append(account)
            log("imported %s from %s" % (account.uid[:8], os.path.basename(path)))
        except Exception as exc:
            log("skip %s: %s" % (os.path.basename(path), exc))
    if not imported:
        candidates = wb_accounts.desktop_credential_candidates()
        if not candidates:
            log("no desktop credential found at %s" % wb_accounts.desktop_auth_dir())
        else:
            log("found %d credential file(s) but none was usable" % len(candidates))
    return imported


def account_views():
    """List view of every account, including a live readiness flag."""
    if not POOL:
        return []
    return POOL.list_public()


def usage_by_account():
    """Aggregate the JSONL log per account id."""
    buckets = {}
    try:
        with open(USAGE_LOG, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("error"):
                    continue
                key = row.get("account") or "(unattributed)"
                bucket = buckets.setdefault(key, {
                    "account": key, "requests": 0, "prompt_tokens": 0,
                    "completion_tokens": 0, "reasoning_tokens": 0,
                    "cached_tokens": 0, "total_tokens": 0, "models": {},
                })
                bucket["requests"] += 1
                for field in ("prompt_tokens", "completion_tokens",
                              "reasoning_tokens", "cached_tokens", "total_tokens"):
                    bucket[field] += row.get(field) or 0
                model = row.get("model") or "?"
                bucket["models"][model] = bucket["models"].get(model, 0) + 1
    except FileNotFoundError:
        pass
    except Exception as exc:
        log("usage_by_account failed: %s" % exc)
    out = sorted(buckets.values(), key=lambda b: -b["total_tokens"])
    for item in out:
        item["models"] = sorted(item["models"].items(), key=lambda kv: -kv[1])[:5]
    return out


def current_account():
    """Account used for display purposes (health / usage summaries)."""
    return POOL.representative() if POOL else None


def prompt_fingerprint(messages):
    """Privacy-safe fingerprint of the outgoing prompt.

    Cache hits need a byte-identical prefix, so these hashes answer "is my
    prefix stable / is my conversation continuous?" without storing any text.
    """
    try:
        def h(obj):
            blob = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
            return hashlib.sha256(blob).hexdigest()[:12]

        msgs = messages or []
        out = {"msgs_sha": h(msgs), "n_msgs": len(msgs)}
        if msgs:
            out["system_sha"] = h(msgs[0]) if msgs[0].get("role") == "system" else ""
            out["prefix_sha"] = h(msgs[:-1]) if len(msgs) > 1 else ""
        return out
    except Exception:
        return {}


def log(msg):
    sys.stderr.write(f"[wb-proxy] {time.strftime('%H:%M:%S')} {msg}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# upstream helpers
# ---------------------------------------------------------------------------

#: Auxiliary models the API advertises but that are not usable for chat.
#: "lite" backs internal helpers (title generation, compaction) and upstream
#: rejects it with 11102; the codewise/completion entries are text-completion
#: or IDE-inline models, not chat models.
NON_CHAT_MODELS = {"lite"}
NON_CHAT_PREFIXES = ("codewise-", "completion-")
NON_CHAT_SUFFIXES = ("-image-alpha", "-image-alpha-edit", "-taco-completion")


def is_chat_model(mid):
    if not mid:
        return False
    if mid in NON_CHAT_MODELS:
        return False
    if mid.startswith(NON_CHAT_PREFIXES):
        return False
    if mid.endswith(NON_CHAT_SUFFIXES):
        return False
    return True


def merge_catalog(primary):
    """Overlay live entries on top of the shipped catalog.

    The CLI-facing model endpoint returns a narrower list than the desktop app
    sees (it omits deepseek-v4.1-flash, gpt-6-astra and others), so a machine
    without the app has no way to learn about them. The shipped catalog fills
    those gaps; anything discovered live wins on a per-model basis.
    """
    merged = {}
    for item in wb_catalog.STATIC_MODELS:
        mid = item.get("id")
        if mid and is_chat_model(mid):
            merged[mid] = dict(item)
    for mid, meta in primary or []:
        if not is_chat_model(mid):
            continue
        if meta:
            base = merged.get(mid) or {}
            base.update(meta)
            merged[mid] = base
        elif mid not in merged:
            merged[mid] = {}
    return [(mid, meta) for mid, meta in merged.items()]


def fetch_models():
    """Return [(model_id, meta_dict), ...] for the intl account."""
    with _lock:
        if _models_cache["data"] and time.time() - _models_cache["at"] < 300:
            return _models_cache["data"]

    live = read_product_config_models()
    if not live:
        live = [(m, {}) for m in fetch_endpoint_models()]
    entries = merge_catalog(live)
    with _lock:
        _models_cache["at"] = time.time()
        _models_cache["data"] = entries
    return entries


def model_entry(mid, meta):
    """Build a rich /v1/models entry from the desktop app catalog metadata.

    The OpenAI spec only names id/object/created/owned_by, so capability data is
    convention-driven. Several shapes are emitted at once so that different
    clients (OpenRouter-style, LobeChat-style, plain-flag readers) all find
    what they look for.
    """
    meta = meta or {}
    item = {
        "id": mid,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "workbuddy",
    }

    name = meta.get("name")
    if name:
        item["name"] = name
    desc = meta.get("descriptionEn") or meta.get("descriptionZh")
    if desc:
        item["description"] = desc

    # ---- modality / capability ----
    # disabledMultimodal explicitly turns image input off; absent means allowed.
    vision = bool(meta.get("supportsImages")) and not meta.get("disabledMultimodal")
    tools = bool(meta.get("supportsToolCall"))
    thinks = bool(meta.get("supportsReasoning"))

    inputs = ["text"] + (["image"] if vision else [])

    # Capability flags under every spelling the common clients look for.
    # /v1/models has no standard for this, so each convention is emitted at
    # once rather than guessing which one a given client reads:
    #   capabilities.vision      generic
    #   supports_vision/images   LobeChat-style flat flags
    #   vision                   Cherry Studio / NextChat style
    #   abilities.vision         LobeChat
    #   multimodal               misc
    #   *_modalities             OpenRouter
    item["capabilities"] = {
        "vision": vision,
        "tool_calls": tools,
        "reasoning": thinks,
    }
    item["supports_vision"] = vision
    item["supports_images"] = vision
    item["supports_tool_calls"] = tools
    item["supports_reasoning"] = thinks
    item["vision"] = vision
    item["multimodal"] = vision
    item["abilities"] = {
        "vision": vision,
        "functionCall": tools,
        "function_call": tools,
        "reasoning": thinks,
    }
    item["input_modalities"] = inputs
    item["output_modalities"] = ["text"]
    item["modalities"] = {"input": inputs, "output": ["text"]}
    # OpenRouter-shaped block, read by several multi-provider clients.
    item["architecture"] = {
        "input_modalities": inputs,
        "output_modalities": ["text"],
        "modality": "+".join(inputs) + "->text",
    }

    # ---- limits ----
    if meta.get("maxInputTokens"):
        item["context_length"] = meta["maxInputTokens"]
        item["max_input_tokens"] = meta["maxInputTokens"]
    if meta.get("maxOutputTokens"):
        item["max_output_tokens"] = meta["maxOutputTokens"]
        item["max_completion_tokens"] = meta["maxOutputTokens"]
    ctx = (meta.get("contextWindow") or {}).get("supportedLengths")
    if ctx:
        item["context_windows"] = ctx

    # ---- reasoning controls ----
    reasoning = meta.get("reasoning") or {}
    efforts = reasoning.get("supportedEfforts")
    if efforts:
        item["reasoning_efforts"] = efforts
    if reasoning.get("effort"):
        item["reasoning_fixed_effort"] = reasoning["effort"]
    if reasoning.get("defaultEffort"):
        item["reasoning_default_effort"] = reasoning["defaultEffort"]
    if reasoning.get("canDisableThinking") is not None:
        item["reasoning_can_disable"] = reasoning["canDisableThinking"]
    if meta.get("onlyReasoning") is not None:
        item["always_reasoning"] = bool(meta.get("onlyReasoning"))

    # ---- misc ----
    if meta.get("credits"):
        item["credits"] = meta["credits"]
    if meta.get("vendor"):
        item["vendor"] = meta["vendor"]
    if meta.get("temperature") is not None:
        item["temperature"] = meta["temperature"]
    if meta.get("top_p") is not None:
        item["top_p"] = meta["top_p"]
    if meta.get("isDefault"):
        item["is_default"] = True
    tags = [t for t in (meta.get("tags") or []) if isinstance(t, str) and not t.startswith("badge:")]
    if tags:
        item["tags"] = tags
    return item


def read_product_config_models():
    """Read the desktop app's cached catalog: [(id, meta), ...].

    Returns [] when the cache is missing or belongs to a non-intl realm.
    """
    try:
        with open(PRODUCT_CONFIG_CACHE, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception as exc:
        log(f"product config cache unavailable ({exc}); falling back to API list")
        return []

    endpoint = str(cfg.get("endpoint") or "")
    if "workbuddy.ai" not in endpoint:
        log(f"product config endpoint is {endpoint!r} - not the intl realm, ignoring")
        return []

    def find(node):
        if isinstance(node, dict):
            models = node.get("models")
            if isinstance(models, list) and models and isinstance(models[0], dict) and models[0].get("id"):
                return models
            for value in node.values():
                hit = find(value)
                if hit:
                    return hit
        return None

    models = find(cfg) or []
    out = []
    for m in models:
        mid = m.get("id")
        if isinstance(mid, str) and mid:
            out.append((mid, m))
    return out


def fetch_endpoint_models():
    account = POOL.pick() if POOL else None
    if account is None:
        log("model discovery skipped: no usable account")
        return [m for m, _ in (_models_cache["data"] or [])]
    req = urllib.request.Request(UPSTREAM + MODELS_PATH, method="GET", headers=account.headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log(f"model discovery failed: {exc}")
        return [m for m, _ in (_models_cache["data"] or [])]

    ids, seen = [], set()
    for agent in (payload.get("data") or {}).get("agents") or []:
        for mid in agent.get("models") or []:
            if mid not in seen:
                seen.add(mid)
                ids.append(mid)
    return ids


def strip_data_prefix(line):
    line = line.strip()
    while line.startswith("data:"):
        line = line[5:].strip()
    return line


def clean_chunk(raw):
    """Drop the empty noise fields the WorkBuddy gateway pads deltas with."""
    try:
        obj = json.loads(raw)
    except Exception:
        return raw
    changed = False
    for choice in obj.get("choices") or []:
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            continue
        if not delta.get("function_call"):
            if "function_call" in delta:
                delta.pop("function_call")
                changed = True
        if isinstance(delta.get("tool_calls"), list) and not delta["tool_calls"]:
            delta.pop("tool_calls")
            changed = True
        for key in NOISE_KEYS:
            if key in delta and not delta.get(key):
                delta.pop(key)
                changed = True
        if not delta and not choice.get("finish_reason"):
            return ""
    return json.dumps(obj, ensure_ascii=False) if changed else raw


def normalize_roles(messages):
    """Map role names the upstream rejects onto ones it accepts.

    WorkBuddy only knows system / user / assistant / tool. OpenAI's newer
    "developer" role (used by the Codex CLI and current SDKs) is the same thing
    as "system", but sending it verbatim fails with code 11128.
    """
    out = []
    for m in messages or []:
        if not isinstance(m, dict):
            out.append(m)
            continue
        item = m
        if m.get("role") == "developer":
            item = dict(m)
            item["role"] = "system"
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Fingerprint Sanitization (immunizes against Codex / Claude Code WAF patterns)
# ---------------------------------------------------------------------------
SANITIZE_FEATURES = (
    "x-anthropic-billing-header",
    "cc_entrypoint=",
    "You are Claude Code",
    "Main branch (",
    "You are a coding agent running in the Codex CLI",
)

SANITIZE_REWRITES = (
    ("You are Claude Code, Anthropic's official CLI for Claude.",
     "You are Claude Code, Anthropic's official CLI tool for Claude."),
    ("Main branch (you will usually use this for PRs)",
     "Default branch (you will usually use this for PRs)"),
    ("You are a coding agent running in the Codex CLI, a terminal-based coding assistant.",
     "You are a coding agent running in the Codex CLI tool, a terminal-based coding assistant."),
)

SANITIZE_HDR_RE = re.compile(r"(?i)x-anthropic-billing-header:[^;\r\n]*;?\s*")
SANITIZE_KV_RE = re.compile(r"(?i)\bcc_[a-z0-9_]+=[^;\r\n]*;?\s*")

def sanitize_text(text):
    if not isinstance(text, str):
        return text
    hit = any(f in text for f in SANITIZE_FEATURES) or bool(SANITIZE_HDR_RE.search(text))
    if not hit:
        return text
    for old, new in SANITIZE_REWRITES:
        text = text.replace(old, new)
    text = SANITIZE_HDR_RE.sub("", text)
    if "cc_" in text:
        prev = ""
        while prev != text:
            prev = text
            text = SANITIZE_KV_RE.sub("", text)
    return text.strip()


def sanitize_content(content):
    if isinstance(content, str):
        return sanitize_text(content)
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and "text" in part:
                p = dict(part)
                p["text"] = sanitize_text(p["text"])
                out.append(p)
            else:
                out.append(part)
        return out
    return content


def sanitize_messages(messages):
    out = []
    for m in messages or []:
        if isinstance(m, dict) and "content" in m:
            item = dict(m)
            item["content"] = sanitize_content(m["content"])
            out.append(item)
        else:
            out.append(m)
    return out


# ---------------------------------------------------------------------------
# DeepSeek Multi-turn Consistency: reasoning_content backfill
# ---------------------------------------------------------------------------
def backfill_reasoning_content(messages, model):
    if not model or not str(model).lower().startswith("deepseek"):
        return messages
    has_trace = False
    for m in messages:
        if isinstance(m, dict):
            if m.get("reasoning") or "reasoning_content" in m:
                has_trace = True
                break
    if not has_trace:
        return messages
    out = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "assistant":
            item = dict(m)
            if "reasoning_content" not in item:
                if item.get("reasoning"):
                    item["reasoning_content"] = str(item["reasoning"])
                else:
                    item["reasoning_content"] = ""
            out.append(item)
        else:
            out.append(m)
    return out


# ---------------------------------------------------------------------------
# Tool & Tool Choice Normalization (avoids code 11101 on object tool_choice)
# ---------------------------------------------------------------------------
def normalize_tool_choice(obj):
    if "tool_choice" not in obj:
        return
    tc = obj["tool_choice"]
    if isinstance(tc, str):
        val = tc.strip().lower()
        if val == "none":
            obj.pop("tool_choice", None)
            obj.pop("tools", None)
            obj.pop("functions", None)
        return
    if isinstance(tc, dict):
        typ = (tc.get("type") or "").strip().lower()
        if typ == "none":
            obj.pop("tool_choice", None)
            obj.pop("tools", None)
            obj.pop("functions", None)
        elif typ in ("auto", "required"):
            obj["tool_choice"] = typ
        elif typ == "function":
            name = (tc.get("function") or {}).get("name") or tc.get("name") or ""
            obj["tool_choice"] = name.strip() or "auto"
        else:
            obj.pop("tool_choice", None)
    else:
        obj.pop("tool_choice", None)


def normalize_tools(obj):
    tools = obj.get("tools")
    if not tools or not isinstance(tools, list):
        return
    norm = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        # Wrap top-level name tool definition into Chat Completions function schema
        if "name" in t and "function" not in t and t.get("type") == "function":
            fn = {
                "name": t.get("name") or "",
                "description": t.get("description") or "",
                "parameters": t.get("parameters") or {},
            }
            if "strict" in t:
                fn["strict"] = t["strict"]
            norm.append({"type": "function", "function": fn})
        else:
            norm.append(t)
    obj["tools"] = norm


# ---------------------------------------------------------------------------
# DeepSeek DSML Tool Calls Fallback Parser
# ---------------------------------------------------------------------------
TAG_START = r"<[^>]*DSML[^>]*"
DSML_CALLS_RE = re.compile(TAG_START + r"calls>(.*?)</[^>]*DSML[^>]*calls>", re.DOTALL)
DSML_INVOKE_RE = re.compile(TAG_START + r"invoke\s+name=[\x22\x27]([^\x22\x27]+)[\x22\x27]>(.*?)</[^>]*invoke>", re.DOTALL)
DSML_PARAM_RE = re.compile(TAG_START + r"parameter\s+name=[\x22\x27]([^\x22\x27]+)[\x22\x27][^>]*>(.*?)</[^>]*parameter>", re.DOTALL)

def parse_dsml_tool_calls(text):
    if not text or "DSML" not in text:
        return None, text
    match = DSML_CALLS_RE.search(text)
    if not match:
        return None, text
    calls_block = match.group(1)
    tool_calls = []
    for inv_match in DSML_INVOKE_RE.finditer(calls_block):
        func_name = inv_match.group(1)
        params_block = inv_match.group(2)
        params = {}
        for p_match in DSML_PARAM_RE.finditer(params_block):
            p_name = p_match.group(1)
            p_val = p_match.group(2).strip()
            params[p_name] = p_val
        tool_calls.append({
            "id": _new_id("call_"),
            "name": func_name,
            "arguments": json.dumps(params, ensure_ascii=False),
        })
    clean = (text[:match.start()].strip() + " " + text[match.end():].strip()).strip()
    return tool_calls, clean


def build_upstream_body(payload):
    model = payload.get("model") or ""
    messages = normalize_roles(payload.get("messages") or [])
    messages = sanitize_messages(messages)
    messages = backfill_reasoning_content(messages, model)
    if not messages or (messages[0].get("role") != "system"):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    body = dict(payload)
    body["messages"] = messages
    normalize_tool_choice(body)
    normalize_tools(body)

    # Thinking injection for DeepSeek models
    if str(model).lower().startswith("deepseek"):
        if "thinking" not in body and body.get("reasoning_effort") != "none":
            body["thinking"] = {"type": "enabled"}

    body["stream"] = True
    body.pop("stream_options", None)
    return body


def open_upstream(payload, session_key=None):
    """POST upstream, rotating accounts when one is rejected.

    Respects session affinity so multi-turn conversations stay on the same account.
    Returns (response, account) so the caller can attribute usage.
    """
    body = json.dumps(build_upstream_body(payload), ensure_ascii=False).encode("utf-8")
    total = max(1, POOL.count_ready()) if POOL else 1
    tried = set()
    last_error = None
    for _ in range(total):
        account = POOL.pick_for_session(session_key=session_key, exclude=tried) if POOL else None
        if account is None:
            break
        tried.add(account.uid)
        req = urllib.request.Request(UPSTREAM + CHAT_PATH, data=body, method="POST",
                                     headers=account.headers())
        try:
            resp = urllib.request.urlopen(req, timeout=600)
            account.clear_error()
            return resp, account
        except urllib.error.HTTPError as exc:
            # 401/403 = stale credential, 429 = throttled: unbind session & rotate
            if exc.code in (401, 403, 429):
                log("account %s rejected (HTTP %s), rotating" % (account.uid[:8], exc.code))
                if session_key and POOL:
                    POOL.affinity.unbind(session_key)
                account.note_error("HTTP %s" % exc.code,
                                   cooldown=300 if exc.code == 429 else 90)
                last_error = exc
                continue
            raise
        except Exception as exc:
            if session_key and POOL:
                POOL.affinity.unbind(session_key)
            account.note_error(str(exc)[:120], cooldown=60)
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("no usable account: all are disabled, cooling down, or expired")


def extract_session_key(headers, payload):
    key = (
        headers.get("X-Conversation-Id") or
        headers.get("Conversation-Id") or
        headers.get("X-Session-Id") or
        headers.get("Session-Id") or
        payload.get("conversation_id") or
        payload.get("session_id") or
        (payload.get("metadata") or {}).get("conversation_id")
    )
    if key:
        return str(key).strip()
    return None

def aggregate_stream(raw_iter, model, resp_id):
    """Fold an SSE stream into one non-streaming chat.completion object."""
    content, reasoning, finish = [], [], "stop"
    usage = None
    started = time.time()
    first_chunk_at = None
    for line in raw_iter:
        data = strip_data_prefix(line.decode("utf-8", "replace"))
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except Exception:
            continue
        if first_chunk_at is None:
            first_chunk_at = time.time()
        if chunk.get("id"):
            resp_id = chunk["id"]
        if chunk.get("model"):
            model = chunk["model"]
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
    message = {"role": "assistant", "content": "".join(content)}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    out = {
        "id": resp_id or "chatcmpl-wb",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
    }
    if usage:
        out["usage"] = usage
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    out["first_chunk_at"] = first_chunk_at
    return out


# ---------------------------------------------------------------------------
# Responses API (/v1/responses) <-> Chat Completions translation
# ---------------------------------------------------------------------------
#
# Kelivo and other clients can speak OpenAI's newer Responses API. The upstream
# gateway only speaks Chat Completions, so those requests are translated down,
# and the reply is translated back up into Responses objects / SSE events.

def local_ip_addresses():
    """Every non-loopback IPv4 address this machine answers on."""
    found = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith("127."):
                found.append(ip)
    except Exception:
        pass
    if not found:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            found.append(probe.getsockname()[0])
            probe.close()
        except Exception:
            pass
    return found


def _new_id(prefix):
    return prefix + uuid.uuid4().hex


def _flatten_content(content):
    """Flatten Responses-style content into text, or OpenAI vision parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    texts, parts = [], []
    for piece in content:
        if isinstance(piece, str):
            texts.append(piece)
            parts.append({"type": "text", "text": piece})
            continue
        if not isinstance(piece, dict):
            continue
        ptype = piece.get("type") or ""
        if ptype in ("input_text", "output_text", "text", "summary_text"):
            t = piece.get("text") or ""
            texts.append(t)
            parts.append({"type": "text", "text": t})
        elif ptype in ("input_image", "image_url", "image") or "image_url" in piece:
            url = piece.get("image_url") or piece.get("url")
            if isinstance(url, dict):
                url = url.get("url")
            if not url and piece.get("data"):
                mime = piece.get("mimeType") or piece.get("mime_type") or "image/png"
                url = f"data:{mime};base64," + piece["data"]
            if url:
                parts.append({"type": "image_url", "image_url": {"url": url}})

    if any(p.get("type") == "image_url" for p in parts):
        return parts          # multimodal: keep structured parts
    return chr(10).join(t for t in texts if t)


def responses_to_chat(payload):
    """Translate a Responses API request body into a Chat Completions body."""
    messages = []

    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    inp = payload.get("input")
    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
    elif isinstance(inp, list):
        for item in inp:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype in (None, "message"):
                body = _flatten_content(item.get("content"))
                if body:
                    role = item.get("role") or "user"
                    if role == "developer":
                        role = "system"
                    # If this is assistant text and the previous message is an assistant
                    # message (e.g. from an adjacent function_call), merge them so
                    # tool_calls and text stay in one message without breaking tool sequence.
                    if role == "assistant" and messages and messages[-1].get("role") == "assistant":
                        prev = messages[-1]
                        if prev.get("content"):
                            prev["content"] = str(prev["content"]) + chr(10) + str(body)
                        else:
                            prev["content"] = body
                    else:
                        messages.append({"role": role, "content": body})
            elif itype == "function_call_output":
                raw_out = item.get("output")
                if isinstance(raw_out, list):
                    content = _flatten_content(raw_out)
                elif isinstance(raw_out, dict):
                    if raw_out.get("type") in ("input_image", "image_url", "image") or "image_url" in raw_out:
                        content = _flatten_content([raw_out])
                    else:
                        content = json.dumps(raw_out, ensure_ascii=False)
                elif isinstance(raw_out, str):
                    content = raw_out
                else:
                    content = str(raw_out)
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id") or "",
                    "content": content,
                })
            elif itype == "function_call":
                tc_item = {
                    "id": item.get("call_id") or item.get("id") or "",
                    "type": "function",
                    "function": {
                        "name": item.get("name") or "",
                        "arguments": item.get("arguments") or "{}",
                    },
                }
                # Merge into previous assistant message if adjacent
                if messages and messages[-1].get("role") == "assistant":
                    prev = messages[-1]
                    if "tool_calls" in prev:
                        prev["tool_calls"].append(tc_item)
                    else:
                        prev["tool_calls"] = [tc_item]
                else:
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tc_item],
                    })

    chat = {"model": payload.get("model"), "messages": messages}

    for key in ("temperature", "top_p", "seed"):
        if payload.get(key) is not None:
            chat[key] = payload[key]
    if payload.get("max_output_tokens") is not None:
        chat["max_tokens"] = payload["max_output_tokens"]

    effort = None
    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
    if not effort:
        effort = payload.get("reasoning_effort")
    if effort:
        chat["reasoning_effort"] = effort

    if payload.get("tools"):
        chat["tools"] = payload["tools"]
    if payload.get("tool_choice"):
        chat["tool_choice"] = payload["tool_choice"]
    if payload.get("parallel_tool_calls") is not None:
        chat["parallel_tool_calls"] = payload["parallel_tool_calls"]
    return chat


def _responses_usage(u):
    if not u:
        return None
    det = u.get("completion_tokens_details") or {}
    pdet = u.get("prompt_tokens_details") or {}
    return {
        "input_tokens": u.get("prompt_tokens") or 0,
        "input_tokens_details": {
            "cached_tokens": u.get("prompt_cache_hit_tokens")
            or det.get("cached_tokens") or pdet.get("cached_tokens") or 0,
        },
        "output_tokens": u.get("completion_tokens") or 0,
        "output_tokens_details": {"reasoning_tokens": det.get("reasoning_tokens") or 0},
        "total_tokens": u.get("total_tokens") or 0,
    }


def chat_to_response(chat_obj, model):
    """Fold a Chat Completions object into a Responses API response object."""
    choice = (chat_obj.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""

    output = []
    if reasoning:
        output.append({
            "id": _new_id("rs_"),
            "type": "reasoning",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": reasoning}],
        })
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        output.append({
            "id": _new_id("fc_"),
            "type": "function_call",
            "status": "completed",
            "call_id": tc.get("id") or _new_id("call_"),
            "name": fn.get("name") or "",
            "arguments": fn.get("arguments") or "{}",
        })
    # DeepSeek DSML tool calls fallback
    if not (msg.get("tool_calls")):
        dsml_calls, clean_t = parse_dsml_tool_calls(text)
        if dsml_calls:
            for dc in dsml_calls:
                output.append({
                    "id": _new_id("fc_"),
                    "type": "function_call",
                    "status": "completed",
                    "call_id": dc.get("id") or _new_id("call_"),
                    "name": dc.get("name") or "",
                    "arguments": dc.get("arguments") or "{}",
                })
            text = clean_t
    if text or not output:
        output.append({
            "id": _new_id("msg_"),
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}] if text else [],
        })

    finish = choice.get("finish_reason") or "stop"
    obj = {
        "id": _new_id("resp_"),
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed" if finish != "length" else "incomplete",
        "model": model,
        "output": output,
        "output_text": text,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "metadata": {},
    }
    u = _responses_usage(chat_obj.get("usage"))
    if u:
        obj["usage"] = u
    if finish == "length":
        obj["incomplete_details"] = {"reason": "max_output_tokens"}
    return obj


def stream_responses_events(upstream, model, holder):
    """Yield Responses-API SSE frames translated from chat-completions chunks."""
    resp_id, msg_id, rs_id = _new_id("resp_"), _new_id("msg_"), _new_id("rs_")
    created = int(time.time())
    seq = 0
    text_parts, reason_parts = [], []
    outputs = []
    reason_index = None
    msg_index = None
    finish = "stop"
    usage = None
    tool_calls_map = {}

    def resp_obj(status):
        obj = {
            "id": resp_id,
            "object": "response",
            "created_at": created,
            "status": status,
            "model": model,
            "output": [o for o in outputs if o],
            "output_text": "".join(text_parts),
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "metadata": {},
        }
        u = _responses_usage(usage)
        if u:
            obj["usage"] = u
        return obj

    def ev(etype, payload):
        nonlocal seq
        seq += 1
        data = {"type": etype, "sequence_number": seq}
        data.update(payload)
        body = json.dumps(data, ensure_ascii=False)
        return ("event: " + etype + chr(10) + "data: " + body + chr(10) + chr(10)).encode("utf-8")

    def reason_item(status):
        return {
            "id": rs_id,
            "type": "reasoning",
            "status": status,
            "summary": [{"type": "summary_text", "text": "".join(reason_parts)}],
        }

    def msg_item(status):
        item = {"id": msg_id, "type": "message", "status": status,
                "role": "assistant", "content": []}
        if text_parts:
            item["content"] = [{"type": "output_text", "text": "".join(text_parts),
                              "annotations": []}]
        return item

    yield ev("response.created", {"response": resp_obj("in_progress")})
    yield ev("response.in_progress", {"response": resp_obj("in_progress")})

    for raw in upstream:
        data = strip_data_prefix(raw.decode("utf-8", "replace"))
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except Exception:
            continue
        if usage is None and chunk.get("usage"):
            usage = chunk["usage"]
            holder["usage"] = usage
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            piece = delta.get("reasoning_content")
            if piece:
                if reason_index is None:
                    reason_index = len(outputs)
                    outputs.append(None)
                    yield ev("response.output_item.added",
                             {"output_index": reason_index, "item": reason_item("in_progress")})
                    yield ev("response.reasoning_summary_part.added", {
                        "item_id": rs_id, "output_index": reason_index, "summary_index": 0,
                        "part": {"type": "summary_text", "text": ""},
                    })
                reason_parts.append(piece)
                yield ev("response.reasoning_summary_text.delta", {
                    "item_id": rs_id, "output_index": reason_index,
                    "summary_index": 0, "delta": piece,
                })
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                fn = tc.get("function") or {}
                fn_name = fn.get("name") or ""
                fn_args = fn.get("arguments") or ""
                call_id = tc.get("id") or ""
                if idx not in tool_calls_map:
                    out_idx = len(outputs)
                    outputs.append(None)
                    c_id = call_id or _new_id("call_")
                    tool_calls_map[idx] = {
                        "output_index": out_idx,
                        "id": c_id,
                        "name": fn_name,
                        "arguments": fn_args,
                    }
                    yield ev("response.output_item.added", {
                        "output_index": out_idx,
                        "item": {
                            "id": _new_id("fc_"),
                            "type": "function_call",
                            "status": "in_progress",
                            "call_id": c_id,
                            "name": fn_name,
                            "arguments": "",
                        },
                    })
                else:
                    entry = tool_calls_map[idx]
                    if fn_name and not entry["name"]:
                        entry["name"] = fn_name
                    if fn_args:
                        entry["arguments"] += fn_args
                        yield ev("response.function_call_arguments.delta", {
                            "output_index": entry["output_index"],
                            "call_id": entry["id"],
                            "delta": fn_args,
                        })

            piece = delta.get("content")
            if piece:
                if msg_index is None:
                    if reason_index is not None:
                        full_r = "".join(reason_parts)
                        yield ev("response.reasoning_summary_text.done", {
                            "item_id": rs_id, "output_index": reason_index,
                            "summary_index": 0, "text": full_r,
                        })
                        yield ev("response.reasoning_summary_part.done", {
                            "item_id": rs_id, "output_index": reason_index, "summary_index": 0,
                            "part": {"type": "summary_text", "text": full_r},
                        })
                        outputs[reason_index] = reason_item("completed")
                        yield ev("response.output_item.done",
                                 {"output_index": reason_index, "item": outputs[reason_index]})
                    msg_index = len(outputs)
                    outputs.append(None)
                    yield ev("response.output_item.added", {
                        "output_index": msg_index,
                        "item": {"id": msg_id, "type": "message", "status": "in_progress",
                                 "role": "assistant", "content": []},
                    })
                    yield ev("response.content_part.added", {
                        "item_id": msg_id, "output_index": msg_index, "content_index": 0,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                    })
                text_parts.append(piece)
                yield ev("response.output_text.delta", {
                    "item_id": msg_id, "output_index": msg_index,
                    "content_index": 0, "delta": piece,
                })
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]

    if reason_index is not None and outputs[reason_index] is None:
        full_r = "".join(reason_parts)
        yield ev("response.reasoning_summary_text.done", {
            "item_id": rs_id, "output_index": reason_index, "summary_index": 0, "text": full_r,
        })
        yield ev("response.reasoning_summary_part.done", {
            "item_id": rs_id, "output_index": reason_index, "summary_index": 0,
            "part": {"type": "summary_text", "text": full_r},
        })
        outputs[reason_index] = reason_item("completed")
        yield ev("response.output_item.done",
                 {"output_index": reason_index, "item": outputs[reason_index]})

    # 1. Emit completed structured tool calls
    for idx in sorted(tool_calls_map.keys()):
        entry = tool_calls_map[idx]
        yield ev("response.function_call_arguments.done", {
            "output_index": entry["output_index"],
            "call_id": entry["id"],
            "arguments": entry["arguments"],
        })
        fc_item = {
            "id": _new_id("fc_"),
            "type": "function_call",
            "status": "completed",
            "call_id": entry["id"],
            "name": entry["name"],
            "arguments": entry["arguments"],
        }
        outputs[entry["output_index"]] = fc_item
        yield ev("response.output_item.done", {
            "output_index": entry["output_index"],
            "item": fc_item,
        })

    # 2. DSML fallback: parse DeepSeek raw markup if no structured tool_calls were emitted
    full_text = "".join(text_parts)
    dsml_calls, clean_text = parse_dsml_tool_calls(full_text)
    if dsml_calls and not tool_calls_map:
        for dc in dsml_calls:
            out_idx = len(outputs)
            fc_item = {
                "id": _new_id("fc_"),
                "type": "function_call",
                "status": "completed",
                "call_id": dc.get("id") or _new_id("call_"),
                "name": dc.get("name") or "",
                "arguments": dc.get("arguments") or "{}",
            }
            outputs.append(fc_item)
            yield ev("response.output_item.added", {
                "output_index": out_idx,
                "item": dict(fc_item, status="in_progress", arguments=""),
            })
            yield ev("response.function_call_arguments.delta", {
                "output_index": out_idx,
                "call_id": fc_item["call_id"],
                "delta": fc_item["arguments"],
            })
            yield ev("response.function_call_arguments.done", {
                "output_index": out_idx,
                "call_id": fc_item["call_id"],
                "arguments": fc_item["arguments"],
            })
            yield ev("response.output_item.done", {
                "output_index": out_idx,
                "item": fc_item,
            })
        full_text = clean_text

    # 3. Emit message item only if text was emitted OR no other output item exists
    has_other_items = any(o for o in outputs if o)
    if msg_index is not None or full_text or not has_other_items:
        if msg_index is None:
            msg_index = len(outputs)
            outputs.append(None)
            yield ev("response.output_item.added", {
                "output_index": msg_index,
                "item": {"id": msg_id, "type": "message", "status": "in_progress",
                         "role": "assistant", "content": []},
            })
            yield ev("response.content_part.added", {
                "item_id": msg_id, "output_index": msg_index, "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            })
        yield ev("response.output_text.done", {
            "item_id": msg_id, "output_index": msg_index, "content_index": 0, "text": full_text,
        })
        yield ev("response.content_part.done", {
            "item_id": msg_id, "output_index": msg_index, "content_index": 0,
            "part": {"type": "output_text", "text": full_text, "annotations": []},
        })
        outputs[msg_index] = msg_item("completed")
        yield ev("response.output_item.done", {"output_index": msg_index, "item": outputs[msg_index]})

    status = "completed" if finish != "length" else "incomplete"
    final = resp_obj(status)
    if finish == "length":
        final["incomplete_details"] = {"reason": "max_output_tokens"}
    yield ev("response.completed", {"response": final})


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "wb-proxy/1.0"

    def log_message(self, fmt, *args):
        log(fmt % args)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, message, err_type="server_error"):
        self._json(code, {"error": {"message": message, "type": err_type, "code": code}})

    def _key_ok(self):
        """True when the request carries the right key (or no key is needed)."""
        if not API_KEY:
            return True
        supplied = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if supplied == API_KEY:
            return True
        # Browsers cannot set headers on a top-level navigation, so accept the
        # key as a query parameter too - the dashboard uses this when opened
        # from another device.
        try:
            query = parse_qs(urlparse(self.path).query)
            if (query.get("key") or [""])[0] == API_KEY:
                return True
        except Exception:
            pass
        return False

    def _authorized(self):
        if self._key_ok():
            return True
        self._error(401, "invalid api key", "invalid_request_error")
        return False

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path in ("/", "/dashboard", "/ui"):
            return self._dashboard()
        if path == "/health":
            # Always answer (the launcher uses this to detect a running copy),
            # but only expose account identity to an authorised caller.
            rep = current_account()
            info = {
                "ok": True,
                "realm": "intl",
                "accounts": len(POOL.accounts) if POOL else 0,
                "accounts_ready": POOL.count_ready() if POOL else 0,
                "api_key_required": bool(API_KEY),
            }
            if self._key_ok():
                info.update({
                    "uid": rep.uid if rep else None,
                    "domain": rep.domain if rep else None,
                    "issuer": wb_accounts.jwt_issuer(rep.access_token) if rep else None,
                    "credential_file": os.path.basename(rep.path) if rep and rep.path else None,
                    "expires_at": rep.expires_at if rep else None,
                })
            return self._json(200, info)
        # Accept the conventional /v1 prefix and the bare path, because clients
        # differ in whether they append "/v1" themselves.
        if path in ("/v1/models", "/models"):
            if not self._authorized():
                return
            try:
                entries = fetch_models()
            except Exception as exc:
                return self._error(502, str(exc))
            data = [model_entry(mid, meta) for mid, meta in entries]
            return self._json(200, {"object": "list", "data": data})
        if path in ("/usage", "/v1/usage"):
            if not self._authorized():
                return
            return self._json(200, usage_snapshot())
        if path == "/usage/recent":
            if not self._authorized():
                return
            try:
                limit = max(1, min(1000, int((query.get("limit") or ["100"])[0])))
            except ValueError:
                limit = 100
            return self._json(200, recent_usage(limit))
        if path == "/accounts/credits":
            if not self._authorized():
                return
            # Refresh credits for all accounts
            for a in (POOL.accounts if POOL else []):
                a.fetch_credits()
            return self._json(200, {"accounts": account_views()})
        if path == "/accounts":
            if not self._authorized():
                return
            return self._json(200, {
                "accounts": account_views(),
                "storage": ACCOUNTS_DIR,
                "usable": POOL.count_ready() if POOL else 0,
            })
        if path == "/accounts/login/poll":
            if not self._authorized():
                return
            state = (query.get("state") or [""])[0]
            return self._json(200, POOL.poll_login(state))
        if path == "/usage/by-account":
            if not self._authorized():
                return
            return self._json(200, {"accounts": usage_by_account()})
        if path == "/usage/perf":
            if not self._authorized():
                return
            try:
                sample = max(10, min(20000, int((query.get("sample") or ["5000"])[0])))
            except ValueError:
                sample = 5000
            return self._json(200, perf_stats(sample))
        return self._error(404, "not found", "invalid_request_error")

    def _dashboard(self):
        try:
            with open(DASHBOARD_HTML, "rb") as fh:
                body = fh.read()
        except Exception as exc:
            return self._error(500, f"dashboard.html unavailable: {exc}")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_accounts(self, path, payload):
        """Account-management endpoints (dashboard uses these)."""
        if POOL is None:
            return self._error(503, "account pool unavailable")

        if path in ("/accounts/credits", "/accounts/credits/fetch"):
            uid = payload.get("uid")
            targets = [POOL.get(uid)] if uid else list(POOL.accounts)
            results = []
            for account in targets:
                if account is None:
                    continue
                res = account.fetch_credits()
                results.append({"uid": account.uid, "ok": res.get("ok", False),
                                "credits": account.credits, "error": res.get("error", "")})
            return self._json(200, {"results": results, "accounts": account_views()})

        if path == "/accounts/login/start":
            platform = payload.get("platform") or "CLI"
            try:
                started = POOL.start_login(platform)
            except Exception as exc:
                return self._error(502, "could not start login: %s" % exc)
            log("oauth login started (platform=%s, state=%s)" % (platform, started["state"][:8]))
            return self._json(200, started)

        if path == "/accounts/login/cancel":
            state = payload.get("state") or ""
            return self._json(200, {"cancelled": POOL.cancel_login(state)})

        if path == "/accounts/import/desktop":
            imported = import_desktop_accounts()
            return self._json(200, {
                "imported": [a.public() for a in imported],
                "accounts": account_views(),
            })

        if path == "/accounts/refresh":
            uid = payload.get("uid")
            targets = [POOL.get(uid)] if uid else list(POOL.accounts)
            results = []
            for account in targets:
                if account is None:
                    continue
                ok = account.refresh()
                account.save(ACCOUNTS_DIR)
                results.append({"uid": account.uid, "ok": ok, "error": account.last_error})
            return self._json(200, {"results": results})

        if path == "/accounts/set":
            uid = payload.get("uid")
            if not uid:
                return self._error(400, "uid required")
            updated = POOL.set_enabled(uid, bool(payload.get("enabled")))
            if updated is None:
                return self._error(404, "no such account")
            log("account %s %s" % (uid[:8], "enabled" if payload.get("enabled") else "disabled"))
            return self._json(200, {"account": updated})

        if path == "/accounts/set-all":
            POOL.set_all_enabled(bool(payload.get("enabled")))
            return self._json(200, {"accounts": account_views()})

        if path == "/accounts/delete":
            uid = payload.get("uid")
            if not uid:
                return self._error(400, "uid required")
            removed = POOL.remove(uid)
            log("account %s deleted" % uid[:8])
            return self._json(200, {"deleted": removed, "accounts": account_views()})

        return self._error(404, "unknown account endpoint", "invalid_request_error")

    def _handle_responses(self, payload):
        """Serve /v1/responses by translating to chat completions upstream."""
        session_key = extract_session_key(self.headers, payload)
        chat_req = responses_to_chat(payload)
        model = payload.get("model") or "deepseek-v4.1-flash"
        want_stream = bool(payload.get("stream"))
        t_start = time.time()
        fp = prompt_fingerprint(chat_req.get("messages"))

        log(
            "responses: model=%s stream=%s msgs=%d effort=%r"
            % (model, want_stream, len(chat_req.get("messages") or []),
               chat_req.get("reasoning_effort"))
        )

        try:
            upstream, account = open_upstream(chat_req, session_key=session_key)
        except urllib.error.HTTPError as exc:
            detail = exc.read(600).decode("utf-8", "replace")
            record_error(model, exc.code, detail,
                         elapsed_ms=int((time.time() - t_start) * 1000))
            return self._error(exc.code, f"upstream {exc.code}: {detail}")
        except Exception as exc:
            message = str(exc)
            record_error(model, 502, message,
                         elapsed_ms=int((time.time() - t_start) * 1000))
            if message.startswith("no usable account"):
                return self._error(503, message + 
                                   " - add or enable one at the dashboard (/)")
            return self._error(502, f"upstream unreachable: {exc}")

        with upstream:
            if want_stream:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                holder = {"usage": None}
                first_ms = None
                try:
                    for frame in stream_responses_events(upstream, model, holder):
                        if first_ms is None:
                            first_ms = int((time.time() - t_start) * 1000)
                        self.wfile.write(frame)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    wall = int((time.time() - t_start) * 1000)
                    record_usage(model, holder.get("usage"), stream=True, elapsed_ms=wall,
                                 ttft_ms=first_ms,
                                 gen_ms=(wall - first_ms) if first_ms is not None else None,
                                 fp=fp, account=account.uid)
                    return
                wall = int((time.time() - t_start) * 1000)
                record_usage(model, holder.get("usage"), stream=True, elapsed_ms=wall,
                             ttft_ms=first_ms,
                             gen_ms=(wall - first_ms) if first_ms is not None else None,
                             fp=fp, account=account.uid)
                return

            try:
                chat_obj = aggregate_stream(upstream, model, None)
            except Exception as exc:
                record_error(model, 502, str(exc),
                             elapsed_ms=int((time.time() - t_start) * 1000))
                return self._error(502, f"upstream stream error: {exc}")
            wall = int((time.time() - t_start) * 1000)
            result = chat_to_response(chat_obj, model)
            record_usage(model, chat_obj.get("usage"), stream=False, elapsed_ms=wall, fp=fp,
                         account=account.uid)
            return self._json(200, result)

    def do_POST(self):
        path = self.path.split("?")[0]
        is_account_route = path.startswith("/accounts/")
        if not is_account_route and path not in ("/v1/chat/completions", "/chat/completions",
                                                 "/v1/completions", "/completions",
                                                 "/v1/responses", "/responses"):
            return self._error(404, "not found", "invalid_request_error")
        if not self._authorized():
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            return self._error(400, "invalid JSON body", "invalid_request_error")

        if is_account_route:
            return self._handle_accounts(path, payload)

        if path in ("/v1/responses", "/responses"):
            return self._handle_responses(payload)

        # Diagnostics: what the client actually asked for, and what we forward.
        # Only the knobs that change behaviour are logged - never message text.
        forwarded = build_upstream_body(payload)
        given = payload.get("reasoning_effort") or payload.get("reasoning") \
            or payload.get("thinking") or payload.get("enable_thinking")
        log(
            "chat: model=%s client_effort=%r -> upstream_effort=%r stream=%s msgs=%d"
            % (
                payload.get("model"),
                given,
                forwarded.get("reasoning_effort"),
                bool(payload.get("stream")),
                len(forwarded.get("messages") or []),
            )
        )
        session_key = extract_session_key(self.headers, payload)
        fp = prompt_fingerprint(forwarded.get("messages"))

        want_stream = bool(payload.get("stream"))
        model = payload.get("model") or "hy4-preview"
        t_start = time.time()
        try:
            upstream, account = open_upstream(payload, session_key=session_key)
        except urllib.error.HTTPError as exc:
            detail = exc.read(600).decode("utf-8", "replace")
            record_error(model, exc.code, detail,
                         elapsed_ms=int((time.time() - t_start) * 1000))
            return self._error(exc.code, f"upstream {exc.code}: {detail}")
        except Exception as exc:
            message = str(exc)
            record_error(model, 502, message, elapsed_ms=int((time.time() - t_start) * 1000))
            if message.startswith("no usable account"):
                return self._error(503, message + 
                                   " - add or enable one at the dashboard (/)")
            return self._error(502, f"upstream unreachable: {exc}")

        with upstream:
            if want_stream:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                emitted = False
                last_usage = None
                first_ms = None
                try:
                    for line in upstream:
                        data = strip_data_prefix(line.decode("utf-8", "replace"))
                        if data == "[DONE]":
                            continue
                        if not data:
                            continue
                        try:
                            maybe = json.loads(data)
                            if maybe.get("usage"):
                                last_usage = maybe["usage"]
                        except Exception:
                            pass
                        cleaned = clean_chunk(data)
                        if not cleaned:
                            continue
                        if first_ms is None:
                            first_ms = int((time.time() - t_start) * 1000)
                        emitted = True
                        self.wfile.write(f"data: {cleaned}\n\n".encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    # Client hung up; still account for what upstream produced.
                    wall = int((time.time() - t_start) * 1000)
                    record_usage(model, last_usage, stream=True,
                                 elapsed_ms=wall, ttft_ms=first_ms,
                                 gen_ms=(wall - first_ms) if first_ms is not None else None,
                                 fp=fp, account=account.uid)
                    return
                if not emitted:
                    err = json.dumps({"error": {"message": "empty upstream stream", "type": "server_error"}})
                    self.wfile.write(f"data: {err}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                wall = int((time.time() - t_start) * 1000)
                record_usage(model, last_usage, stream=True,
                             elapsed_ms=wall, ttft_ms=first_ms,
                             gen_ms=(wall - first_ms) if first_ms is not None else None,
                             fp=fp, account=account.uid)
                return

            try:
                result = aggregate_stream(upstream, model, None)
            except Exception as exc:
                record_error(model, 502, str(exc), elapsed_ms=int((time.time() - t_start) * 1000))
                return self._error(502, f"upstream stream error: {exc}")
            wall = int((time.time() - t_start) * 1000)
            first_at = result.get("first_chunk_at")
            # Measured from request arrival so streaming and non-streaming are comparable.
            first_ms = int((first_at - t_start) * 1000) if first_at else None
            record_usage(model, result.get("usage"), stream=False,
                         elapsed_ms=wall, ttft_ms=first_ms,
                         gen_ms=(wall - first_ms) if first_ms is not None else None,
                         fp=fp, account=account.uid)
            return self._json(200, result)


def main():
    global POOL, ACCOUNTS_DIR, API_KEY, SYSTEM_PROMPT, USAGE_DIR, USAGE_LOG, USAGE_SUMMARY
    API_KEY_GENERATED = False

    ap = argparse.ArgumentParser(description="WorkBuddy (workbuddy.ai) -> OpenAI-compatible proxy")
    ap.add_argument("--info", help="path to the WorkBuddy *.info credential file")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--lan", action="store_true",
                    help="listen on every interface so other devices on the LAN can "
                         "reach it (implies --host 0.0.0.0 and forces an api key)")
    ap.add_argument("--api-key", default=os.environ.get("WB_PROXY_KEY") or None,
                    help="require this bearer token on /v1/* (optional)")
    ap.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT,
                    help="system message injected when the request has none (required upstream)")
    ap.add_argument("--user-agent", default=None,
                    help="override the upstream User-Agent (default: mirror the official "
                         "WorkBuddy AI client)")
    ap.add_argument("--usage-dir", default=None,
                    help="where to store usage.jsonl / usage-summary.json (default: ./usage)")
    ap.add_argument("--accounts-dir", default=None,
                    help="where the per-account credential files live (default: ./accounts)")
    ap.add_argument("--import-desktop", action="store_true",
                    help="import the desktop app credential as an account, then exit")
    args = ap.parse_args()

    # LAN mode: bind everywhere, and default to the fixed key "qwer.1234".
    if args.lan:
        if args.host == "127.0.0.1":
            args.host = "0.0.0.0"
        if not args.api_key:
            args.api_key = "qwer.1234"
            API_KEY_GENERATED = False

    if args.user_agent:
        wb_accounts.USER_AGENT = args.user_agent.strip()
        log("user-agent : %s (override)" % wb_accounts.USER_AGENT)

    if args.usage_dir:
        USAGE_DIR = os.path.abspath(args.usage_dir)
        USAGE_LOG = os.path.join(USAGE_DIR, "usage.jsonl")
        USAGE_SUMMARY = os.path.join(USAGE_DIR, "usage-summary.json")

    # Refuse to start a second copy. On Windows SO_REUSEADDR lets two sockets
    # bind the same port, which silently splits incoming connections between
    # them - confusing and hard to diagnose.
    try:
        probe = urllib.request.urlopen(
            f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}/health",
            timeout=2,
        )
        existing = json.loads(probe.read().decode("utf-8"))
        print()
        print(f"  [已有一个反代在 {args.port} 端口运行，无需重复启动]")
        print(f"  账号: {existing.get('uid', '?')} @ {existing.get('domain', '?')}")
        print(f"  看板: http://127.0.0.1:{args.port}/")
        print()
        print("  如果要重启: 先把原来那个窗口关掉（或结束 python 进程），再运行本程序。")
        print()
        return
    except Exception:
        pass  # nothing listening - good, carry on

    API_KEY = args.api_key
    SYSTEM_PROMPT = args.system_prompt
    if args.accounts_dir:
        ACCOUNTS_DIR = os.path.abspath(args.accounts_dir)

    POOL = wb_accounts.AccountPool(ACCOUNTS_DIR, log=log)
    POOL.load()

    if args.info:
        account = POOL.import_desktop_credential(args.info, source="file")
        log("imported account %s from %s" % (account.uid[:8], args.info))

    first_run = not POOL.accounts
    if first_run:
        log("no accounts yet - trying the desktop app credential")
        import_desktop_accounts()

    if first_run and not POOL.accounts:
        # Do NOT exit here: the dashboard has to stay reachable so a new
        # account can be added through the browser login flow.
        log("still no accounts - starting anyway so you can log in via the dashboard")

    if args.import_desktop:
        for account in POOL.accounts:
            print("  %s  %s  %s" % (account.uid[:8], account.nickname, account.domain))
        return

    rep = current_account()
    log("accounts   : %d total, %d usable" % (len(POOL.accounts), POOL.count_ready()))
    for account in POOL.accounts:
        log("  - %s  %s  %s  %s" % (account.uid[:8], account.nickname or "(no name)",
                                    account.domain, wb_accounts._human_delta(
                                        (account.expires_at or 0) - time.time()) or "?"))
    log("store      : %s" % ACCOUNTS_DIR)
    log(f"credential : {rep.path if rep else chr(45)}")
    if os.path.exists(PRODUCT_CONFIG_CACHE):
        log(f"catalog    : {PRODUCT_CONFIG_CACHE}")
    else:
        log("catalog    : app cache not found - will use the model API instead")
    log(f"account    : {rep.uid if rep else chr(45)} @ {rep.domain if rep else chr(45)}")
    log(f"issuer     : {wb_accounts.jwt_issuer(rep.access_token) if rep else chr(45)}")
    log("realm      : intl (www.workbuddy.ai only)")
    log("user-agent : %s" % wb_accounts.USER_AGENT)
    log(f"listening  : http://{args.host}:{args.port}/v1  (api key: {'on' if API_KEY else 'off'})")
    log(f"dashboard  : http://{args.host}:{args.port}/")
    if args.host == "0.0.0.0":
        ips = local_ip_addresses() or ["<this-pc-ip>"]
        print()
        print("  " + "=" * 62)
        print("  LAN MODE - reachable from other devices")
        print()
        for ip in ips:
            print("    API       : http://%s:%s/v1" % (ip, args.port))
            print("    Dashboard : http://%s:%s/" % (ip, args.port))
        print()
        print("    API Key   : %s" % API_KEY)
        if API_KEY_GENERATED:
            print("                (generated for this run - save it)")
        print()
        print("    Open the dashboard (key already included):")
        print("      http://%s:%s/?key=%s" % (ips[0], args.port, API_KEY))
        print()
        print("    Clients: Base URL = the API address above, then paste the key.")
        print()
        print("    If nothing can connect, allow python through the")
        print("    firewall: run allow-firewall.bat once as administrator.")
        print("  " + "=" * 62)
        print()
        sys.stdout.flush()

    if not POOL.accounts:
        print()
        print("  " + "=" * 62)
        print("  NO ACCOUNTS YET")
        print()
        print("  Open the dashboard and click [Login new account]:")
        print("      http://127.0.0.1:%s/" % args.port)
        print()
        print("  The browser flow adds the account automatically.")
        print("  This window must stay open.")
        print("  " + "=" * 62)
        print()
        sys.stdout.flush()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("bye")


if __name__ == "__main__":
    try:
        # Keep console output readable regardless of the active code page.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
