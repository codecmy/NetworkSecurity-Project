"""Tests for HTML-content-derived features using a local HTTP server."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from networksecurity.utils.feature_extraction.extractor import PhishingFeatureExtractor

PHISHY_HTML = """<!DOCTYPE html>
<html>
<head>
  <link rel="icon" href="http://evil.example/favicon.ico">
  <link rel="stylesheet" href="http://evil.example/style.css">
  <script src="http://evil.example/hook.js"></script>
  <meta http-equiv="refresh" content="0; url=http://evil.example/steal">
</head>
<body oncontextmenu="return false;">
  <a href="http://evil.example/click">link1</a>
  <a href="#fake">link2</a>
  <a href="/same">link3</a>
  <a href="https://same-host-local.test/local">link4</a>
  <form action="http://evil.example/submit" method="POST">
    <input type="text" name="user">
  </form>
  <form action="mailto:steal@evil.example">
    <input type="submit">
  </form>
  <img src="http://evil.example/pixel.png">
  <img src="/local.png">
  <iframe src="http://evil.example/frame" frameborder="0"></iframe>
  <script>
    window.open("http://evil.example/pop");
    window.open("http://evil.example/pop2");
    window.open("http://evil.example/pop3");
    window.open("http://evil.example/pop4");
  </script>
  <script>prompt("enter your password");</script>
  <a href="#" onmouseover="window.status='http://safe.example'; return true;">hover</a>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PHISHY_HTML.encode("utf-8"))

    def log_message(self, *args):  # silence
        pass


@pytest.fixture(scope="module")
def html_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/index.html"
    server.shutdown()


@pytest.fixture()
def html_extractor():
    return PhishingFeatureExtractor(fetch_html=True, request_timeout=5.0)


def test_html_features(html_server, html_extractor):
    features = html_extractor.extract(html_server)
    assert features["Favicon"] == -1.0
    assert features["RightClick"] == -1.0
    assert features["popUpWidnow"] == -1.0
    assert features["Iframe"] == -1.0
    assert features["Submitting_to_email"] == -1.0
    # SFH: first form posts to a different domain -> 0
    assert features["SFH"] == 0.0
    # URL_of_Anchor: 4 anchors, 3 are off-page/empty -> ratio 0.75 -> -1
    assert features["URL_of_Anchor"] == -1.0
    # Links_in_tags: link+script both external -> ratio 1.0 -> -1
    assert features["Links_in_tags"] == -1.0
    # Request_URL: img external vs local -> 0.5 -> 0
    assert features["Request_URL"] == 0.0
    # on_mouseover with window.status -> -1
    assert features["on_mouseover"] == -1.0
    # meta refresh (1) + 4 window.open -> 5 redirects -> 1
    assert features["Redirect"] == 1.0
    # IP-hosted page
    assert features["having_IP_Address"] == -1.0


def test_html_unavailable_returns_nan(monkeypatch):
    extractor = PhishingFeatureExtractor(fetch_html=True, request_timeout=0.1)
    monkeypatch.setattr(extractor, "_fetch_html", lambda url: None)
    monkeypatch.setattr(extractor, "_dns_record", lambda hostname: 1)
    monkeypatch.setattr(extractor, "_get_whois", lambda hostname: None)
    features = extractor.extract("http://example.com")
    assert features["Favicon"] != features["Favicon"]  # NaN
    assert features["Iframe"] != features["Iframe"]  # NaN
    assert features["Request_URL"] != features["Request_URL"]  # NaN
    assert features["having_IP_Address"] == 1.0
