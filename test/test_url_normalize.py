import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from scripts import url_normalize


def test_remove_tracking_and_fragment():
    url = "https://Example.COM/path?utm_source=google&fbclid=ABC123&keep=1#section"
    normalized = url_normalize.normalize_url(url)
    assert "fbclid" not in normalized
    assert "utm_source" not in normalized
    assert "#" not in normalized
    assert normalized.endswith("/path?keep=1") or normalized.endswith("/path")


def test_sort_query_and_default_port():
    url = "http://Example.com:80/a?b=2&a=1"
    normalized = url_normalize.normalize_url(url)
    assert normalized.startswith("http://example.com")
    # default port removed
    assert ":80" not in normalized
    # query params sorted
    assert "?a=1&b=2" in normalized


def test_trailing_slash_behavior():
    url1 = "https://example.com/foo/"
    url2 = "https://example.com/foo"
    n1 = url_normalize.normalize_url(url1)
    n2 = url_normalize.normalize_url(url2)
    assert n1.endswith("/foo/")
    assert n2.endswith("/foo")


def test_stable_hash_for_same_normalized_url():
    a = "https://example.com/path?b=2&a=1&utm_campaign=x"
    b = "https://EXAMPLE.com:443/path?a=1&b=2#frag"
    na = url_normalize.normalize_url(a)
    nb = url_normalize.normalize_url(b)
    assert na == nb
    ha = url_normalize.make_entry_hash(na)
    hb = url_normalize.make_entry_hash(nb)
    assert ha == hb


def test_invalid_url_raises():
    with pytest.raises(ValueError):
        url_normalize.normalize_url("//missing-scheme.com/path")
    with pytest.raises(ValueError):
        url_normalize.normalize_url("http:///no-host")
