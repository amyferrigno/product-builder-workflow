"""In-memory fake of the Jira Cloud REST v3 calls used by scripts/jira_client.py."""

import json
import re
from collections import namedtuple
from urllib.parse import urlparse

Request = namedtuple("Request", ["method", "path", "body"])

JQL_PATTERN = re.compile(
    r'^project = "((?:[^"\\]|\\.)*)" AND labels = "((?:[^"\\]|\\.)*)"$'
)


def _unescape(value):
    return re.sub(r"\\(.)", r"\1", value)


def _response(status, payload=None, headers=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    return status, dict(headers or {}), body


class FakeJira:
    def __init__(self, project_key="DEMO"):
        self.project_key = project_key
        self.issues = {}
        self.requests = []
        self._counter = 0
        self._created = []
        self._fail_next = []
        self._fail_on = {}

    # Failure injection

    def fail_next(self, status, times=1, headers=None):
        for _ in range(times):
            self._fail_next.append((status, headers))

    def fail_on_request(self, n, status, headers=None):
        """Fail the n-th request received (1-based, counting every request)."""
        self._fail_on[n] = (status, headers)

    # Seeding and helpers

    def _new_key(self):
        self._counter += 1
        return "{}-{}".format(self.project_key, self._counter)

    def seed_issue(self, fields):
        key = self._new_key()
        self.issues[key] = dict(fields)
        return key

    def created_keys(self):
        return list(self._created)

    def count(self, method, path_prefix):
        return sum(
            1 for r in self.requests
            if r.method == method and r.path.startswith(path_prefix)
        )

    # Transport

    def transport(self, method, url, headers, body, timeout):
        path = urlparse(url).path
        parsed = json.loads(body.decode("utf-8")) if body else None
        self.requests.append(Request(method, path, parsed))
        number = len(self.requests)

        if not any(k.lower() == "authorization" and v for k, v in headers.items()):
            return _response(401, {"errorMessages": ["Unauthorized"]})

        if number in self._fail_on:
            status, extra = self._fail_on.pop(number)
            return _response(status, {"errorMessages": ["injected failure"]}, extra)
        if self._fail_next:
            status, extra = self._fail_next.pop(0)
            return _response(status, {"errorMessages": ["injected failure"]}, extra)

        if method == "POST" and path == "/rest/api/3/search/jql":
            return self._search(parsed or {})
        if method == "POST" and path == "/rest/api/3/issue":
            return self._create(parsed or {})
        if method == "PUT" and path.startswith("/rest/api/3/issue/"):
            return self._update(path[len("/rest/api/3/issue/"):], parsed or {})
        return _response(404, {"errorMessages": ["not found"]})

    def _search(self, body):
        match = JQL_PATTERN.match(body.get("jql", ""))
        if not match:
            return _response(400, {"errorMessages": ["unsupported JQL"]})
        project, label = (_unescape(g) for g in match.groups())
        found = []
        for key, fields in self.issues.items():
            if key.split("-")[0] == project and label in fields.get("labels", []):
                found.append({
                    "key": key,
                    "id": str(10000 + int(key.rsplit("-", 1)[1])),
                    "fields": {
                        "summary": fields.get("summary", ""),
                        "labels": fields.get("labels", []),
                    },
                })
        return _response(200, {"issues": found[: body.get("maxResults", 50)]})

    def _create(self, body):
        fields = body.get("fields")
        if not isinstance(fields, dict):
            return _response(400, {"errorMessages": ["fields required"]})
        if (fields.get("project") or {}).get("key") != self.project_key:
            return _response(400, {"errors": {"project": "invalid project"}})
        if not fields.get("summary"):
            return _response(400, {"errors": {"summary": "summary is required"}})
        if not (fields.get("issuetype") or {}).get("name"):
            return _response(400, {"errors": {"issuetype": "issue type is required"}})
        parent = (fields.get("parent") or {}).get("key")
        if parent is not None and parent not in self.issues:
            return _response(400, {"errors": {"parent": "unknown parent " + str(parent)}})
        key = self.seed_issue(fields)
        self._created.append(key)
        return _response(201, {
            "id": str(10000 + self._counter),
            "key": key,
            "self": "https://fake.atlassian.net/rest/api/3/issue/" + key,
        })

    def _update(self, key, body):
        if key not in self.issues:
            return _response(404, {"errorMessages": ["Issue does not exist"]})
        self.issues[key].update(body.get("fields", {}))
        return _response(204)
