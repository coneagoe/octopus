from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import hashlib

TRACKING_KEYS = {
    "fbclid",
    "ref",
    "spm",
    "scene",
    "from",
    "share",
    "channel",
}


def _is_tracking_key(key: str) -> bool:
    # Be tolerant to non-string keys and treat keys case-insensitively
    if not isinstance(key, str):
        return False
    k = key.lower()
    if k in TRACKING_KEYS:
        return True
    if k.startswith("utm_"):
        return True
    return False


def normalize_url(url: str) -> str:
    """Normalize a URL according to the project's dedup rules.

    Rules implemented:
    - Lower-case scheme and host
    - Remove default ports 80 (http) and 443 (https)
    - Remove tracking params (fbclid, ref, spm, scene, from, share, channel, utm_*)
    - Keep meaningful params
    - Sort remaining query params by key then value
    - Preserve trailing slash if present; do not add one if absent
    - Remove fragment
    - Raise ValueError for invalid absolute URLs (missing scheme or netloc)
    """
    if not isinstance(url, str):
        raise ValueError("url must be a string")

    split = urlsplit(url)
    scheme = split.scheme.lower()
    hostname = split.hostname.lower() if split.hostname else None

    if not scheme or not hostname:
        raise ValueError(f"Invalid absolute URL: {url}")

    # Rebuild netloc with optional userinfo and port (remove default ports)
    netloc = ""
    if split.username:
        netloc += split.username
        if split.password:
            netloc += ":" + split.password
        netloc += "@"

    netloc += hostname

    port = split.port
    if port is not None:
        if not (scheme == "http" and port == 80) and not (scheme == "https" and port == 443):
            netloc += f":{port}"

    # Query: remove tracking params and sort
    qsl = parse_qsl(split.query, keep_blank_values=True)
    filtered = [(k, v) for (k, v) in qsl if not _is_tracking_key(k)]
    # Sort by key then value
    filtered.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(filtered, doseq=True)

    # Preserve path as-is to keep trailing slash behavior
    path = split.path

    normalized = urlunsplit((scheme, netloc, path, query, ""))
    return normalized


def make_entry_hash(normalized_url: str) -> str:
    if not isinstance(normalized_url, str):
        raise ValueError("normalized_url must be a string")
    h = hashlib.sha256()
    h.update(normalized_url.encode("utf-8"))
    return h.hexdigest()
