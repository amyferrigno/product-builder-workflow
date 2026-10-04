"""Test scripts/jira_client.py against the in-memory fake (no network)."""

import base64
import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from fake_jira import FakeJira  # noqa: E402
from jira_client import JiraClient, JiraError, to_adf  # noqa: E402

SITE = "https://example.atlassian.net"
EMAIL = "someone@example.com"
TOKEN = "s3cr3t-token-value"


def make_client(fake=None, **kwargs):
    fake = fake or FakeJira()
    delays = []
    kwargs.setdefault("min_interval", 0)
    client = JiraClient(SITE, EMAIL, TOKEN, transport=fake.transport, sleep=delays.append, **kwargs)
    return client, fake, delays


def issue_fields(summary="A story", labels=None, **extra):
    fields = {
        "project": {"key": "DEMO"},
        "summary": summary,
        "issuetype": {"name": "Story"},
        "labels": labels or [],
    }
    fields.update(extra)
    return fields


# Happy paths

def test_create_returns_key_and_stores_issue():
    client, fake, _ = make_client()
    key = client.create_issue(issue_fields("First"))
    assert key == "DEMO-1"
    assert fake.issues[key]["summary"] == "First"
    assert fake.created_keys() == ["DEMO-1"]
    assert fake.requests[0].body == {"fields": issue_fields("First")}


def test_create_with_known_parent():
    client, fake, _ = make_client()
    epic = client.create_issue(issue_fields("Epic"))
    child = client.create_issue(issue_fields("Child", parent={"key": epic}))
    assert fake.issues[child]["parent"] == {"key": epic}


def test_search_by_label_finds_matching_issues():
    client, fake, _ = make_client()
    seeded = fake.seed_issue(issue_fields("Seeded", labels=["pm-abc"]))
    fake.seed_issue(issue_fields("Other", labels=["pm-other"]))
    result = client.search_by_label("DEMO", "pm-abc")
    assert [r["key"] for r in result] == [seeded]
    assert set(result[0]) == {"key", "id"}
    request = fake.requests[0]
    assert (request.method, request.path) == ("POST", "/rest/api/3/search/jql")
    assert request.body == {
        "jql": 'project = "DEMO" AND labels = "pm-abc"',
        "fields": ["summary", "labels"],
        "maxResults": 50,
    }


def test_search_no_match_returns_empty_list():
    client, _, _ = make_client()
    assert client.search_by_label("DEMO", "nothing") == []


def test_update_issue_succeeds_on_204():
    client, fake, _ = make_client()
    key = fake.seed_issue(issue_fields("Old"))
    assert client.update_issue(key, {"summary": "New"}) is None
    assert fake.issues[key]["summary"] == "New"
    request = fake.requests[0]
    assert (request.method, request.path) == ("PUT", "/rest/api/3/issue/" + key)
    assert request.body == {"fields": {"summary": "New"}}


def test_update_unknown_key_raises_404_at_once():
    client, fake, delays = make_client()
    with pytest.raises(JiraError) as excinfo:
        client.update_issue("DEMO-99", {"summary": "x"})
    assert excinfo.value.status == 404
    assert len(fake.requests) == 1
    assert delays == []


def test_headers_sent():
    seen = {}

    def transport(method, url, headers, body, timeout):
        seen.update(headers=headers, url=url)
        return 200, {}, b'{"issues": []}'

    JiraClient(SITE + "/", EMAIL, TOKEN, transport=transport, sleep=lambda s: None,
               min_interval=0).search_by_label("DEMO", "x")
    expected = "Basic " + base64.b64encode((EMAIL + ":" + TOKEN).encode()).decode()
    assert seen["headers"]["Authorization"] == expected
    assert seen["headers"]["Accept"] == "application/json"
    assert seen["headers"]["Content-Type"] == "application/json"
    assert seen["url"] == SITE + "/rest/api/3/search/jql"


def test_fake_rejects_missing_authorization():
    fake = FakeJira()
    status, _, _ = fake.transport("POST", SITE + "/rest/api/3/issue", {}, b"{}", 1)
    assert status == 401


# JQL escaping

def test_jql_values_are_escaped():
    client, fake, _ = make_client()
    key = fake.seed_issue(issue_fields("Tricky", labels=['a"b\\c']))
    result = client.search_by_label("DEMO", 'a"b\\c')
    assert fake.requests[0].body["jql"] == 'project = "DEMO" AND labels = "a\\"b\\\\c"'
    assert [r["key"] for r in result] == [key]


# Retries

def test_429_with_retry_after_is_retried_and_honoured():
    client, fake, delays = make_client()
    fake.fail_next(429, headers={"Retry-After": "7"})
    assert client.create_issue(issue_fields()) == "DEMO-1"
    assert delays == [7]
    assert len(fake.requests) == 2


def test_retry_after_is_capped_at_30():
    client, fake, delays = make_client()
    fake.fail_next(429, headers={"Retry-After": "500"})
    client.create_issue(issue_fields())
    assert delays == [30]


def test_500_on_search_retried_with_backoff_sequence():
    client, fake, delays = make_client()
    fake.fail_next(500, times=3)
    assert client.search_by_label("DEMO", "a") == []
    assert delays == [1, 2, 4]
    assert fake.count("POST", "/rest/api/3/search/jql") == 4


def test_500_on_create_is_not_retried():
    client, fake, delays = make_client()
    fake.fail_next(500)
    with pytest.raises(JiraError) as excinfo:
        client.create_issue(issue_fields())
    assert excinfo.value.status == 500
    assert fake.count("POST", "/rest/api/3/issue") == 1
    assert delays == []


def test_backoff_is_capped_at_30():
    client, fake, delays = make_client(max_retries=8)
    fake.fail_next(503, times=8)
    client.search_by_label("DEMO", "a")
    assert delays == [1, 2, 4, 8, 16, 30, 30, 30]


def test_retries_are_bounded_then_jira_error():
    client, fake, delays = make_client(max_retries=3)
    fake.fail_next(500, times=10)
    with pytest.raises(JiraError) as excinfo:
        client.search_by_label("DEMO", "a")
    assert excinfo.value.status == 500
    assert len(fake.requests) == 4
    assert delays == [1, 2, 4]


def test_400_raises_at_once_without_retry():
    client, fake, delays = make_client()
    with pytest.raises(JiraError) as excinfo:
        client.create_issue(issue_fields(parent={"key": "DEMO-404"}))
    assert excinfo.value.status == 400
    assert len(fake.requests) == 1
    assert delays == []


def test_fail_on_request_targets_the_nth_request():
    client, fake, delays = make_client()
    fake.fail_on_request(2, 500)
    client.search_by_label("DEMO", "a")
    client.search_by_label("DEMO", "b")
    assert delays == [1]
    assert len(fake.requests) == 3


def test_network_errors_retried_then_status_zero():
    calls = []

    def transport(method, url, headers, body, timeout):
        calls.append(1)
        raise TimeoutError("timed out")

    delays = []
    client = JiraClient(SITE, EMAIL, TOKEN, transport=transport, sleep=delays.append,
                        min_interval=0, max_retries=2)
    with pytest.raises(JiraError) as excinfo:
        client.search_by_label("DEMO", "a")
    assert excinfo.value.status == 0
    assert len(calls) == 3
    assert delays == [1, 2]


def test_network_error_on_create_is_not_retried():
    calls = []

    def transport(method, url, headers, body, timeout):
        calls.append(1)
        raise TimeoutError("timed out")

    client = JiraClient(SITE, EMAIL, TOKEN, transport=transport, sleep=lambda s: None, min_interval=0)
    with pytest.raises(JiraError) as excinfo:
        client.create_issue(issue_fields())
    assert excinfo.value.status == 0
    assert "network error" in str(excinfo.value)
    assert len(calls) == 1


def test_network_error_then_success():
    state = {"n": 0}

    def transport(method, url, headers, body, timeout):
        state["n"] += 1
        if state["n"] == 1:
            raise OSError("connection reset")
        return 200, {}, json.dumps({"issues": []}).encode()

    client = JiraClient(SITE, EMAIL, TOKEN, transport=transport, sleep=lambda s: None, min_interval=0)
    assert client.search_by_label("DEMO", "a") == []


# Minimum interval

def test_min_interval_enforced_between_requests():
    client, fake, delays = make_client(min_interval=0.5)
    client.search_by_label("DEMO", "a")
    assert delays == []  # first request does not wait
    client.search_by_label("DEMO", "b")
    assert len(delays) == 1
    assert 0 < delays[0] <= 0.5


def test_zero_min_interval_never_sleeps():
    client, _, delays = make_client(min_interval=0)
    client.search_by_label("DEMO", "a")
    client.search_by_label("DEMO", "b")
    assert delays == []


# Secrets and validation

def test_error_text_never_contains_token_or_email():
    client, fake, _ = make_client(max_retries=1)
    fake.fail_next(500, times=5)
    with pytest.raises(JiraError) as excinfo:
        client.search_by_label("DEMO", "a")
    error = excinfo.value
    for text in (str(error), repr(error), error.message):
        assert TOKEN not in text
        assert EMAIL not in text
        assert "Authorization" not in text
        assert "Basic" not in text
    assert "POST" in str(error) and "/rest/api/3/search/jql" in str(error) and "500" in str(error)


def test_error_body_echoing_credentials_is_redacted():
    credential = base64.b64encode("{}:{}".format(EMAIL, TOKEN).encode()).decode()

    def transport(method, url, headers, body, timeout):
        echo = "Authorization: {} user {} token {}".format(headers["Authorization"], EMAIL, TOKEN)
        return 400, {}, echo.encode()

    client = JiraClient(SITE, EMAIL, TOKEN, transport=transport, sleep=lambda s: None, min_interval=0)
    with pytest.raises(JiraError) as excinfo:
        client.create_issue(issue_fields())
    error = excinfo.value
    assert "[redacted]" in str(error)
    for text in (str(error), repr(error)):
        assert TOKEN not in text and EMAIL not in text and credential not in text


def test_error_body_is_truncated_to_300_chars():
    def transport(method, url, headers, body, timeout):
        return 400, {}, b"x" * 1000

    client = JiraClient(SITE, EMAIL, TOKEN, transport=transport, sleep=lambda s: None, min_interval=0)
    with pytest.raises(JiraError) as excinfo:
        client.create_issue(issue_fields())
    assert str(excinfo.value).count("x") == 300


@pytest.mark.parametrize("site", ["http://example.atlassian.net", "example.atlassian.net", "", "https://"])
def test_non_https_site_rejected(site):
    with pytest.raises(ValueError):
        JiraClient(site, EMAIL, TOKEN, transport=FakeJira().transport)


def test_trailing_slash_site_normalised():
    seen = []

    def transport(method, url, headers, body, timeout):
        seen.append(url)
        return 200, {}, b'{"issues": []}'

    JiraClient(SITE + "///", EMAIL, TOKEN, transport=transport, min_interval=0).search_by_label("D", "x")
    assert seen == [SITE + "/rest/api/3/search/jql"]


def test_default_transport_never_used_with_fake(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("urlopen must not be called in tests")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    client, fake, _ = make_client()
    key = client.create_issue(issue_fields(labels=["l"]))
    client.update_issue(key, {"summary": "y"})
    assert client.search_by_label("DEMO", "l")[0]["key"] == key


# ADF

def test_to_adf_paragraphs():
    doc = to_adf("First para\n\nSecond para")
    assert doc["type"] == "doc" and doc["version"] == 1
    assert [n["type"] for n in doc["content"]] == ["paragraph", "paragraph"]
    assert doc["content"][1]["content"] == [{"type": "text", "text": "Second para"}]


def test_to_adf_bullet_list():
    doc = to_adf("Intro\n- one\n- two\n\n- solo")
    types = [n["type"] for n in doc["content"]]
    assert types == ["paragraph", "bulletList", "bulletList"]
    items = doc["content"][1]["content"]
    assert len(items) == 2
    assert items[0] == {
        "type": "listItem",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "one"}]}],
    }


def test_to_adf_empty_text_gives_one_empty_paragraph():
    for text in ("", "   \n\n  ", None):
        assert to_adf(text) == {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": []}],
        }
