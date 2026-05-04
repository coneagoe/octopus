import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from scripts import url_normalize


class TestUrlNormalize:
    def test_remove_tracking_and_fragment(self):
        url = "https://Example.COM/path?utm_source=google&fbclid=ABC123&keep=1#section"
        normalized = url_normalize.normalize_url(url)
        assert normalized == "https://example.com/path?keep=1"

    def test_sort_query_and_default_port(self):
        url = "http://Example.com:80/a?b=2&a=1"
        normalized = url_normalize.normalize_url(url)
        assert normalized == "http://example.com/a?a=1&b=2"

    def test_trailing_slash_behavior(self):
        url1 = "https://example.com/foo/"
        url2 = "https://example.com/foo"
        n1 = url_normalize.normalize_url(url1)
        n2 = url_normalize.normalize_url(url2)
        assert n1 == "https://example.com/foo/"
        assert n2 == "https://example.com/foo"

    def test_stable_hash_for_same_normalized_url(self):
        a = "https://example.com/path?b=2&a=1&utm_campaign=x"
        b = "https://EXAMPLE.com:443/path?a=1&b=2#frag"
        na = url_normalize.normalize_url(a)
        nb = url_normalize.normalize_url(b)
        assert na == "https://example.com/path?a=1&b=2"
        assert na == nb
        ha = url_normalize.make_entry_hash(na)
        hb = url_normalize.make_entry_hash(nb)
        assert ha == hb

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            url_normalize.normalize_url("//missing-scheme.com/path")
        with pytest.raises(ValueError):
            url_normalize.normalize_url("http:///no-host")
