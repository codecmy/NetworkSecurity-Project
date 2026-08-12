"""
Real-time phishing feature extractor.

Reimplements the 30 features of the UCI "Phishing Websites" dataset (same
{-1, 0, 1} encodings used to train the model) from a raw URL and, where
possible, live DNS / SSL / WHOIS / page-HTML signals.

Features that cannot be computed (no network, whois blocked, HTML not
fetchable, or data only available from paid feeds such as Alexa / PageRank /
Google index / backlinks / statistical blacklists) are left as ``NaN``. The
trained preprocessor is a ``KNNImputer`` pipeline, so missing features are
imputed at predict time.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import tldextract
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from networksecurity.exception.exception import NetworkSecurityException

import sys

FEATURE_NAMES: List[str] = [
    "having_IP_Address",
    "URL_Length",
    "Shortining_Service",
    "having_At_Symbol",
    "double_slash_redirecting",
    "Prefix_Suffix",
    "having_Sub_Domain",
    "SSLfinal_State",
    "Domain_registeration_length",
    "Favicon",
    "port",
    "HTTPS_token",
    "Request_URL",
    "URL_of_Anchor",
    "Links_in_tags",
    "SFH",
    "Submitting_to_email",
    "Abnormal_URL",
    "Redirect",
    "on_mouseover",
    "RightClick",
    "popUpWidnow",
    "Iframe",
    "age_of_domain",
    "DNSRecord",
    "web_traffic",
    "Page_Rank",
    "Google_Index",
    "Links_pointing_to_page",
    "Statistical_report",
]

#: URL shortener domains used by feature 3.
SHORTENERS = {
    "bit.ly", "goo.gl", "t.co", "tinyurl.com", "ow.ly", "is.gd", "buff.ly",
    "adf.ly", "tiny.cc", "cutt.ly", "rebrand.ly", "rb.gy", "shorturl.at",
    "soo.gd", "s.id", "tiny.pl", "lnkd.in", "db.tt", "qr.ae", "v.gd",
    "short.io", "zurl.co", "surl.li", "shortcm.li", "bl.ink", "x.co",
}

#: Ports considered "standard" for feature 11.
STANDARD_PORTS = {21, 22, 23, 25, 53, 80, 110, 119, 143, 389, 443, 445, 993, 995}

HTML_TAG_ATTRS = (
    ("img", "src"),
    ("audio", "src"),
    ("video", "src"),
    ("embed", "src"),
    ("source", "src"),
)

_INVISIBLE_IFRAME_RE = re.compile(
    r"<iframe[^>]*\sframeborder\s*=\s*[\"']?0[\"']?[^>]*>", re.IGNORECASE
)
_ONMOUSEOVER_RE = re.compile(
    r"onmouseover[^>]*?\bstatus\s*[=:]", re.IGNORECASE
)
_WINDOW_OPEN_RE = re.compile(
    r"(?:window\.)?open\s*\(\s*[\"'][^\"']*[\"']", re.IGNORECASE
)


class _DomainCache:
    """Tiny thread-safe TTL cache for slow per-domain lookups."""

    def __init__(self, ttl: float = 900.0) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._store: Dict[str, tuple] = {}

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            with self._lock:
                self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)


class PhishingFeatureExtractor:
    """
    Extracts the 30 phishing-dataset features from a raw URL.

    Example:
        >>> ex = PhishingFeatureExtractor()
        >>> features = ex.extract("http://example.com/login.php")
        >>> len(features)
        30
    """

    def __init__(
        self,
        request_timeout: float = 8.0,
        resolve_timeout: float = 5.0,
        whois_timeout: float = 6.0,
        cache_ttl: float = 900.0,
        fetch_html: bool = True,
        use_whois: bool = True,
    ) -> None:
        self.request_timeout = request_timeout
        self.resolve_timeout = resolve_timeout
        self.whois_timeout = whois_timeout
        self.fetch_html = fetch_html
        self.use_whois = use_whois
        self._dns = _DomainCache(cache_ttl)
        self._ssl = _DomainCache(cache_ttl)
        self._whois_cache = _DomainCache(cache_ttl)
        self._tld_cache = tldextract.TLDExtract()

    # ------------------------------------------------------------------ URL
    def _parse(self, url: str):
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().strip(".")
        if parsed.port is None:
            port = None
        else:
            port = parsed.port
        ext = self._tld_cache(url)
        return parsed, hostname, port, ext

    def _having_ip_address(self, hostname: str) -> int:
        try:
            ipaddress.ip_address(hostname)
            return -1
        except ValueError:
            return 1

    def _url_length(self, url: str) -> int:
        length = len(url)
        if length < 54:
            return 1
        if 54 <= length <= 75:
            return 0
        return -1

    def _shortening_service(self, hostname: str) -> int:
        top = self._tld_cache(hostname).top_domain_under_public_suffix or ""
        if top in SHORTENERS or hostname in SHORTENERS:
            return -1
        return 1

    def _having_at_symbol(self, url: str) -> int:
        return -1 if "@" in url else 1

    def _double_slash_redirecting(self, url: str, parsed) -> int:
        after_protocol = url.split("://", 1)
        rest = after_protocol[1] if len(after_protocol) > 1 else url
        if parsed.scheme and "://" in url:
            rest = url.split("://", 1)[1]
        return -1 if "//" in rest else 1

    def _prefix_suffix(self, hostname: str) -> int:
        return -1 if "-" in hostname else 1

    def _having_sub_domain(self, ext) -> int:
        sub = (ext.subdomain or "").lower()
        if sub in ("", "www", "m", "mobile"):
            levels = 0
        else:
            levels = sub.count(".") + 1
        if levels == 0:
            return 1
        if levels == 1:
            return 0
        return -1

    def _port(self, port: Optional[int]) -> int:
        if port is None:
            return 1
        return -1 if port not in STANDARD_PORTS else 1

    def _https_token(self, hostname: str, scheme: str) -> int:
        return -1 if "https" in hostname.lower() else 1

    def _abnormal_url(self, url: str, hostname: str) -> int:
        if "@" in url:
            return -1
        if not hostname:
            return -1
        return 1

    # ------------------------------------------------------------ network
    def _dns_record(self, hostname: str) -> int:
        cached = self._dns.get(hostname)
        if cached is not None:
            return cached
        try:
            socket.setdefaulttimeout(self.resolve_timeout)
            socket.gethostbyname(hostname)
            value = 1
        except Exception:
            value = -1
        self._dns.set(hostname, value)
        return value

    def _ssl_state(self, hostname: str) -> Optional[int]:
        """
        Encoding follows the training CSV: +1 = HTTPS with a trusted cert
        (legitimate), 0 = HTTPS but trust/age cannot be confirmed (suspicious),
        -1 = plain HTTP (phishing signal).
        """
        cached = self._ssl.get(hostname)
        if cached is not None:
            return cached
        cert = self._get_cert(hostname)
        if cert is None:
            value = 0  # https but trust cannot be verified -> suspicious
        else:
            age_days = self._cert_age_days(cert.get("notBefore"))
            if age_days is not None and age_days >= 365 * 2:
                value = 1
            else:
                value = 0
        self._ssl.set(hostname, value)
        return value

    def _cert_age_days(self, not_before: Optional[str]) -> Optional[float]:
        if not not_before:
            return None
        try:
            parsed = datetime.strptime(not_before, "%b %d %H:%M:%S %Y %Z")
        except ValueError:
            return None
        return (datetime.utcnow() - parsed).days

    def _get_cert(self, hostname: str) -> Optional[dict]:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=self.resolve_timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as s:
                    return s.getpeercert()
        except Exception:
            return None

    def _get_whois(self, hostname: str):
        if not self.use_whois:
            return None
        cached = self._whois_cache.get(hostname)
        if cached is not None:
            return cached
        value = self._fetch_whois(hostname)
        self._whois_cache.set(hostname, value)
        return value

    def _fetch_whois(self, hostname: str):
        try:
            import whois as whois_client

            record = whois_client.whois(hostname)
            if record is None:
                return None
            text = str(record)
            if text in ("None", "", "{}", "\\N"):
                return None
            return record
        except Exception:
            return None

    def _domain_registration_length(self, whois_record) -> Optional[int]:
        """
        Training CSV encoding: -1 = registered for a year or longer
        (legitimate), +1 = short registration (phishing signal).
        """
        created = self._first_date(whois_record, "creation_date")
        expires = self._first_date(whois_record, "expiration_date")
        if created is None or expires is None:
            return None
        if (expires - created).days <= 365:
            return 1
        return -1

    def _age_of_domain(self, whois_record) -> Optional[int]:
        created = self._first_date(whois_record, "creation_date")
        if created is None:
            return None
        if (datetime.utcnow() - created).days < 30 * 6:
            return -1
        return 1

    @staticmethod
    def _first_date(whois_record, attr: str) -> Optional[datetime]:
        try:
            value = getattr(whois_record, attr, None)
            if isinstance(value, list):
                value = value[0] if value else None
            if isinstance(value, datetime):
                if value.tzinfo is not None:
                    value = value.replace(tzinfo=None)
                return value
            if value:
                return datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except Exception:
            return None
        return None

    # --------------------------------------------------------------- HTML
    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            import requests

            response = requests.get(url, timeout=self.request_timeout, allow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type and "xml" not in content_type:
                return None
            return response.text[:2_000_000]
        except Exception:
            return None

    def _favicon(self, soup, hostname: str) -> Optional[int]:
        for link in soup.find_all("link"):
            rel = link.get("rel") or []
            if isinstance(rel, str):
                rel_text = rel.lower()
            else:
                rel_text = " ".join(rel).lower()
            if "icon" not in rel_text:
                continue
            href = link.get("href")
            if not href:
                continue
            icon_host = urlparse(href).hostname
            if icon_host and icon_host.lower() != hostname:
                return -1
            return 1
        return 1

    def _external_ratio(self, soup, hostname: str, tags, attr: str) -> Optional[float]:
        total = 0
        external = 0
        for tag in soup.find_all(tags):
            value = tag.get(attr)
            if not value:
                continue
            total += 1
            src_host = urlparse(value).hostname
            if src_host and src_host.lower() != hostname:
                external += 1
        if total == 0:
            return None
        return external / total

    def _request_url(self, soup, hostname: str) -> Optional[int]:
        counts: Dict[str, float] = {}
        for tag, attr in HTML_TAG_ATTRS:
            ratio = self._external_ratio(soup, hostname, tag, attr)
            if ratio is not None:
                counts[tag] = ratio
        if not counts:
            return None
        total = sum(counts.values()) / len(counts)
        if total < 0.22:
            return 1
        if total <= 0.61:
            return 0
        return -1

    def _url_of_anchor(self, soup, hostname: str) -> Optional[int]:
        anchors = soup.find_all("a")
        if not anchors:
            return 1
        suspicious = 0
        for a in anchors:
            href = a.get("href")
            if not href or href.strip().startswith(("#", "javascript:", "mailto:")):
                suspicious += 1
                continue
            href = href.strip()
            if href in ("about:blank",):
                suspicious += 1
                continue
            if href.startswith(("http://", "https://")):
                if urlparse(href).hostname and urlparse(href).hostname.lower() != hostname:
                    suspicious += 1
        ratio = suspicious / len(anchors)
        if ratio < 0.31:
            return 1
        if ratio <= 0.67:
            return 0
        return -1

    def _links_in_tags(self, soup, hostname: str) -> Optional[int]:
        ratios = []
        for tag, attr in (("link", "href"), ("script", "src")):
            ratio = self._external_ratio(soup, hostname, tag, attr)
            if ratio is not None:
                ratios.append(ratio)
        if not ratios:
            return None
        ratio = sum(ratios) / len(ratios)
        if ratio < 0.17:
            return 1
        if ratio <= 0.81:
            return 0
        return -1

    def _sfh(self, soup, hostname: str) -> Optional[int]:
        form = soup.find("form")
        if form is None:
            return 1
        action = (form.get("action") or "").strip()
        if not action or action in ("about:blank", "#", "javascript:void(0)"):
            return -1
        action_host = urlparse(action).hostname
        if action_host and action_host.lower() != hostname:
            return 0
        return 1

    def _submitting_to_email(self, soup) -> Optional[int]:
        for form in soup.find_all("form"):
            action = (form.get("action") or "").lower()
            if "mailto:" in action:
                return -1
        return 1

    def _redirect(self, soup, html: str) -> Optional[int]:
        count = 0
        for meta in soup.find_all("meta", attrs={"http-equiv": re.compile("refresh", re.I)}):
            count += 1
        count += len(_WINDOW_OPEN_RE.findall(html))
        if count <= 1:
            return -1
        if count <= 4:
            return 0
        return 1

    def _on_mouseover(self, html: str) -> Optional[int]:
        return -1 if _ONMOUSEOVER_RE.search(html) else 1

    def _right_click(self, html: str) -> Optional[int]:
        return -1 if re.search(r"oncontextmenu\s*=", html, re.IGNORECASE) else 1

    def _pop_up_window(self, html: str) -> Optional[int]:
        if re.search(r"prompt\s*\(", html) or re.search(r"createPopup", html, re.IGNORECASE):
            return -1
        return 1

    def _iframe(self, html: str) -> Optional[int]:
        return -1 if _INVISIBLE_IFRAME_RE.search(html) else 1

    # ------------------------------------------------------------ public
    def extract(self, url: str) -> Dict[str, float]:
        """
        Extract all 30 features for a single URL.

        Returns a dict keyed by feature name. Missing values are ``np.nan``
        and are imputed by the KNNImputer preprocessor at predict time.
        """
        try:
            url = url.strip()
            if not url.lower().startswith(("http://", "https://")):
                url = "http://" + url

            parsed, hostname, port, ext = self._parse(url)
            scheme = parsed.scheme.lower()

            dns_record = self._dns_record(hostname)
            whois_record = self._get_whois(hostname)

            html: Optional[str] = None
            soup: Optional[BeautifulSoup] = None
            if self.fetch_html:
                html = self._fetch_html(url)
                if html is not None:
                    soup = BeautifulSoup(html, "html.parser")

            features: Dict[str, float] = {
                "having_IP_Address": float(self._having_ip_address(hostname)),
                "URL_Length": float(self._url_length(url)),
                "Shortining_Service": float(self._shortening_service(hostname)),
                "having_At_Symbol": float(self._having_at_symbol(url)),
                "double_slash_redirecting": float(self._double_slash_redirecting(url, parsed)),
                "Prefix_Suffix": float(self._prefix_suffix(hostname)),
                "having_Sub_Domain": float(self._having_sub_domain(ext)),
                "SSLfinal_State": self._ssl_state(hostname) if scheme == "https" else -1.0,
                "Domain_registeration_length": self._domain_registration_length(whois_record),
                "Favicon": self._favicon(soup, hostname) if soup is not None else np.nan,
                "port": float(self._port(port)),
                "HTTPS_token": float(self._https_token(hostname, scheme)),
                "Request_URL": self._request_url(soup, hostname) if soup is not None else np.nan,
                "URL_of_Anchor": self._url_of_anchor(soup, hostname) if soup is not None else np.nan,
                "Links_in_tags": self._links_in_tags(soup, hostname) if soup is not None else np.nan,
                "SFH": self._sfh(soup, hostname) if soup is not None else np.nan,
                "Submitting_to_email": self._submitting_to_email(soup) if soup is not None else np.nan,
                "Abnormal_URL": float(self._abnormal_url(url, hostname)),
                "Redirect": self._redirect(soup, html) if soup is not None else np.nan,
                "on_mouseover": self._on_mouseover(html) if html is not None else np.nan,
                "RightClick": self._right_click(html) if html is not None else np.nan,
                "popUpWidnow": self._pop_up_window(html) if html is not None else np.nan,
                "Iframe": self._iframe(html) if html is not None else np.nan,
                "age_of_domain": self._age_of_domain(whois_record),
                "DNSRecord": float(dns_record),
                "web_traffic": np.nan,
                "Page_Rank": np.nan,
                "Google_Index": np.nan,
                "Links_pointing_to_page": np.nan,
                "Statistical_report": np.nan,
            }

            for name in FEATURE_NAMES:
                value = features.get(name)
                if value is None:
                    features[name] = np.nan
                elif not isinstance(value, float):
                    features[name] = float(value)

            return features
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e

    def extract_dataframe(self, urls: List[str]) -> "pd.DataFrame":
        """Extract features for a list of URLs, returning a DataFrame in schema order."""
        import pandas as pd

        rows = [self.extract(url) for url in urls]
        df = pd.DataFrame(rows, columns=FEATURE_NAMES)
        return df[FEATURE_NAMES]
