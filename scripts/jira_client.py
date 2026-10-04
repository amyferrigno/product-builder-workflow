#!/usr/bin/env python3
"""Minimal Jira Cloud REST v3 client (standard library only).

Only the calls the publisher needs: search by label, create issue, update issue.
Credentials are passed in by the caller and never appear in error messages.
"""

import base64
import json
import re
import time
import urllib.error
import urllib.request

MAX_BACKOFF_SECONDS = 30
MAX_BODY_CHARS = 300
REQUEST_TIMEOUT_SECONDS = 30


class JiraError(Exception):
    """A failed Jira call. Message holds method, path, status and a short body excerpt."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def default_transport(method, url, headers, body, timeout):
    """Send one request with urllib. HTTP error statuses are returned, not raised.

    Network-level failures (URLError, timeout) propagate as OSError subclasses.
    """
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read()
        finally:
            exc.close()
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, payload


def _jql_quote(value):
    """Escape backslashes and double quotes for a JQL string value."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _header(headers, name):
    lowered = name.lower()
    for key, value in (headers or {}).items():
        if key.lower() == lowered:
            return value
    return None


class JiraClient:
    def __init__(self, site, email, token, transport=None, sleep=time.sleep,
                 min_interval=0.2, max_retries=5):
        if not isinstance(site, str) or not site.startswith("https://") or len(site.rstrip("/")) <= len("https://"):
            raise ValueError("Jira site must be an https:// URL")
        self.site = site.rstrip("/")
        credentials = "{}:{}".format(email, token).encode("utf-8")
        self._auth = "Basic " + base64.b64encode(credentials).decode("ascii")
        self._transport = transport if transport is not None else default_transport
        self._sleep = sleep
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request_at = None

    def _wait_for_interval(self):
        if self._last_request_at is None or self.min_interval <= 0:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    @staticmethod
    def _retry_delay(attempt, headers):
        delay = min(2 ** attempt, MAX_BACKOFF_SECONDS)
        raw = _header(headers, "Retry-After")
        if raw is not None:
            try:
                delay = min(max(float(raw), 0), MAX_BACKOFF_SECONDS)
            except (TypeError, ValueError):
                pass
        return delay

    def _request(self, method, path, payload=None):
        url = self.site + path
        headers = {
            "Authorization": self._auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        attempt = 0
        while True:
            self._wait_for_interval()
            try:
                status, resp_headers, resp_body = self._transport(
                    method, url, headers, body, REQUEST_TIMEOUT_SECONDS)
                failure = None
            except OSError as exc:
                status, resp_headers, resp_body = 0, {}, b""
                failure = type(exc).__name__
            self._last_request_at = time.monotonic()

            if failure is None and 200 <= status < 300:
                return resp_body
            retryable = failure is not None or status == 429 or status >= 500
            if not retryable:
                raise JiraError(status, self._message(method, path, status, resp_body))
            if attempt >= self.max_retries:
                raise JiraError(status, self._message(method, path, status, resp_body, failure))
            self._sleep(self._retry_delay(attempt, resp_headers))
            attempt += 1

    @staticmethod
    def _message(method, path, status, body, failure=None):
        text = body.decode("utf-8", errors="replace")[:MAX_BODY_CHARS] if body else ""
        if failure:
            text = "network error: " + failure
        return "Jira {} {} failed with status {}: {}".format(method, path, status, text)

    @staticmethod
    def _json(raw):
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            return {}

    def search_by_label(self, project_key, label):
        jql = 'project = "{}" AND labels = "{}"'.format(_jql_quote(project_key), _jql_quote(label))
        raw = self._request("POST", "/rest/api/3/search/jql", {
            "jql": jql,
            "fields": ["summary", "labels"],
            "maxResults": 50,
        })
        issues = self._json(raw).get("issues", [])
        return [{"key": issue["key"], "id": issue["id"]} for issue in issues]

    def create_issue(self, fields):
        raw = self._request("POST", "/rest/api/3/issue", {"fields": fields})
        key = self._json(raw).get("key")
        if not key:
            raise JiraError(0, "Jira POST /rest/api/3/issue returned no issue key")
        return key

    def update_issue(self, key, fields):
        self._request("PUT", "/rest/api/3/issue/{}".format(key), {"fields": fields})


def _text_node(text):
    return {"type": "text", "text": text}


def _paragraph(lines):
    content = []
    for index, line in enumerate(lines):
        if index:
            content.append({"type": "hardBreak"})
        if line:
            content.append(_text_node(line))
    return {"type": "paragraph", "content": content}


def _bullet_list(items):
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [_paragraph([item])]} for item in items
        ],
    }


def to_adf(text):
    """Convert plain text to Atlassian Document Format.

    Blank-line separated blocks become paragraphs; lines starting with "- " become bullet lists.
    """
    content = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        if not block.strip():
            continue
        paragraph_lines = []
        bullets = []
        for line in block.split("\n"):
            line = line.rstrip()
            if line.startswith("- "):
                if paragraph_lines:
                    content.append(_paragraph(paragraph_lines))
                    paragraph_lines = []
                bullets.append(line[2:])
            else:
                if bullets:
                    content.append(_bullet_list(bullets))
                    bullets = []
                paragraph_lines.append(line)
        if bullets:
            content.append(_bullet_list(bullets))
        if paragraph_lines:
            content.append(_paragraph(paragraph_lines))
    if not content:
        content.append({"type": "paragraph", "content": []})
    return {"type": "doc", "version": 1, "content": content}
