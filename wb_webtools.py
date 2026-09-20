# -*- coding: utf-8 -*-
"""wb_webtools.py - 反代內建 web_search / web_fetch

背景：Codex App 會宣告 web_search / web_fetch 這兩個 Responses 工具，但
WorkBuddy 上游並沒有這種服務端工具（16 個模型全都沒有 supports_search_tool）。
所以工具宣告送上去、模型看得到、卻沒有執行器，呼叫時 App 一律回
"unsupported call"。

做法（概念參考 CiderCC-UwU proxy.mjs 的 internal web tools，後端完全換掉，
因為 WorkBuddy 沒有 /alpha/web-search 這種路由）：

  1. 客戶端宣告 web_search 時，反代主動注入 web_search + web_fetch 兩個
     function 定義，模型才看得到。
  2. 模型呼叫這兩個工具時，反代不把 function_call 送給客戶端，而是在本地
     執行（DuckDuckGo 搜尋 / 抓網頁），把結果當 tool message 餵回模型。
  3. 客戶端從頭到尾只看到一個連續的回答。

只用 Python 標準庫，沒有額外依賴。
"""
import html as _html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

WEB_SEARCH_NAME = "web_search"
WEB_FETCH_NAME = "web_fetch"

_WEB_TOOL_TYPES = ("web_search", "web_search_preview", "web_fetch")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_FETCH_CHARS = 100000
MAX_RESULTS = 10
MAX_WEB_ROUNDS = 3
HTTP_TIMEOUT = 20


def web_search_tool_def():
    return {
        "type": "function",
        "function": {
            "name": WEB_SEARCH_NAME,
            "description": (
                "Searches the web for real-time information and returns ranked "
                "results with titles, URLs and snippets. Use it for current events, "
                "documentation lookup, or anything beyond your knowledge cutoff. "
                "To read a specific result in full, call web_fetch on its URL afterwards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "numResults": {
                        "type": "number",
                        "description": "How many results to return (1-10, default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    }


def web_fetch_tool_def():
    return {
        "type": "function",
        "function": {
            "name": WEB_FETCH_NAME,
            "description": (
                "Fetches a URL and returns its readable text content. "
                "Use it to read a page found via web_search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute http:// or https:// URL to fetch.",
                    },
                    "startIndex": {
                        "type": "number",
                        "description": "Character offset to continue reading a long page.",
                    },
                },
                "required": ["url"],
            },
        },
    }


def wants_web_tools(tools):
    """客戶端有沒有宣告 web 搜尋類工具。"""
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("type") or "").lower() in _WEB_TOOL_TYPES:
            return True
    return False


def is_internal_tool(name):
    return str(name or "").strip() in (WEB_SEARCH_NAME, WEB_FETCH_NAME)


def _http_get(url, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, "replace")
    except Exception:
        return raw.decode("utf-8", "replace")


def _strip_tags(text):
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _ddg_redirect_target(href):
    """DuckDuckGo 的結果連結是 //duckduckgo.com/l/?uddg=<encoded>，解回真網址。"""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = urllib.parse.parse_qs(parsed.query)
            target = (qs.get("uddg") or [""])[0]
            if target:
                return urllib.parse.unquote(target)
    except Exception:
        pass
    return href


def web_search(query, num_results=5):
    """DuckDuckGo HTML 版搜尋。回傳人類可讀字串（直接餵給模型）。"""
    query = str(query or "").strip()
    if len(query) < 2:
        return "Error: web_search needs a query of at least 2 characters."
    try:
        n = int(num_results)
    except Exception:
        n = 5
    n = max(1, min(MAX_RESULTS, n))

    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        page = _http_get(url)
    except urllib.error.HTTPError as exc:
        return "Error: search backend returned HTTP %s." % exc.code
    except Exception as exc:
        return "Error: could not reach the search backend (%s)." % type(exc).__name__

    blocks = re.split(r'(?is)<div[^>]+class="[^"]*result__body[^"]*"', page)
    results = []
    for block in blocks[1:]:
        m_link = re.search(r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block)
        if not m_link:
            continue
        href = _ddg_redirect_target(m_link.group(1))
        title = _strip_tags(m_link.group(2))
        m_snip = re.search(r'(?is)class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', block)
        snippet = _strip_tags(m_snip.group(1)) if m_snip else ""
        if not href or not title:
            continue
        results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= n:
            break

    if not results:
        return ("No results found for: %s\n\nTry a broader or differently worded query." % query)

    lines = []
    for i, r in enumerate(results, 1):
        lines.append("%d. %s\n   %s\n   %s" % (i, r["title"], r["url"], r["snippet"]))
    return ("Search results for: %s\n\n%s\n\nCite the sources you used at the end of your answer."
            % (query, "\n\n".join(lines)))


def web_fetch(url, start_index=0):
    """抓取網頁並轉成可讀文字。"""
    url = str(url or "").strip()
    if not url:
        return "Error: web_fetch needs a url."
    if not re.match(r"(?i)^https?://", url):
        return "Error: only absolute http:// or https:// URLs are supported."

    try:
        page = _http_get(url)
    except urllib.error.HTTPError as exc:
        return "Error: %s returned HTTP %s." % (url, exc.code)
    except Exception as exc:
        return "Error: could not fetch %s (%s)." % (url, type(exc).__name__)

    text = _strip_tags(page)
    try:
        start = max(0, int(start_index))
    except Exception:
        start = 0
    if start >= len(text):
        return ("Error: startIndex %d is past the end of the page (%d characters total)."
                % (start, len(text)))

    end = min(start + MAX_FETCH_CHARS, len(text))
    body = text[start:end]
    head = "URL: %s\nCharacters: %d-%d of %d" % (url, start, end, len(text))
    tail = ""
    if end < len(text):
        tail = "\n\n[Truncated. Call web_fetch again with startIndex=%d to continue.]" % end
    return head + "\n\n" + body + tail


def execute_web_tool(name, args_raw):
    """執行內部 web 工具，回傳要餵回模型的字串。永不拋例外。"""
    name = str(name or "").strip()
    args = {}
    if isinstance(args_raw, str):
        try:
            args = json.loads(args_raw or "{}")
        except Exception:
            args = {}
    elif isinstance(args_raw, dict):
        args = args_raw
    if not isinstance(args, dict):
        args = {}

    try:
        if name == WEB_SEARCH_NAME:
            return web_search(args.get("query"), args.get("numResults") or 5)
        if name == WEB_FETCH_NAME:
            return web_fetch(args.get("url"), args.get("startIndex") or 0)
        return "Error: unknown internal tool %s." % name
    except Exception as exc:
        return "Error running %s: %s" % (name, exc)
