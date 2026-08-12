"""Unit tests for the phishing feature extractor (URL-derived features only)."""

import pytest

from networksecurity.utils.feature_extraction.extractor import (
    FEATURE_NAMES,
    PhishingFeatureExtractor,
)


@pytest.fixture()
def offline_extractor(monkeypatch):
    """Extractor with network-dependent lookups stubbed out."""
    extractor = PhishingFeatureExtractor(fetch_html=False)
    monkeypatch.setattr(extractor, "_dns_record", lambda hostname: 1)
    monkeypatch.setattr(extractor, "_get_whois", lambda hostname: None)
    monkeypatch.setattr(extractor, "_ssl_state", lambda hostname: 0)
    return extractor


def test_feature_names_order_and_count(offline_extractor):
    features = offline_extractor.extract("http://example.com")
    assert len(features) == 30
    assert list(features.keys()) == FEATURE_NAMES
    assert all(key in features for key in FEATURE_NAMES)


def test_having_ip_address(offline_extractor):
    features = offline_extractor.extract("http://192.168.1.1/evil.php")
    assert features["having_IP_Address"] == -1.0


def test_not_ip_address(offline_extractor):
    features = offline_extractor.extract("http://example.com/")
    assert features["having_IP_Address"] == 1.0


def test_url_length_ranges(offline_extractor):
    short = offline_extractor.extract("http://example.com/")
    assert short["URL_Length"] == 1.0
    long_url = "https://" + "very-long-path/" * 12
    assert offline_extractor.extract(long_url)["URL_Length"] == -1.0


def test_shortening_service(offline_extractor):
    assert offline_extractor.extract("https://bit.ly/abc123")["Shortining_Service"] == -1.0
    assert offline_extractor.extract("http://tinyurl.com/yf3k")["Shortining_Service"] == -1.0
    assert offline_extractor.extract("http://example.com/")["Shortining_Service"] == 1.0


def test_having_at_symbol(offline_extractor):
    assert offline_extractor.extract("http://www.example.com@evil.com/")["having_At_Symbol"] == -1.0
    assert offline_extractor.extract("http://example.com/")["having_At_Symbol"] == 1.0


def test_double_slash_redirecting(offline_extractor):
    assert offline_extractor.extract("http://example.com//evil")["double_slash_redirecting"] == -1.0
    assert offline_extractor.extract("http://example.com/evil")["double_slash_redirecting"] == 1.0


def test_prefix_suffix(offline_extractor):
    assert offline_extractor.extract("http://pay-pal.com-secure.example/")["Prefix_Suffix"] == -1.0
    assert offline_extractor.extract("http://example.com/")["Prefix_Suffix"] == 1.0


def test_port(offline_extractor):
    assert offline_extractor.extract("http://example.com:8080/")["port"] == -1.0
    assert offline_extractor.extract("http://example.com:80/")["port"] == 1.0
    assert offline_extractor.extract("http://example.com/")["port"] == 1.0


def test_https_token(offline_extractor):
    assert offline_extractor.extract("http://https.example.com/")["HTTPS_token"] == -1.0
    assert offline_extractor.extract("http://example.com/")["HTTPS_token"] == 1.0


def test_abnormal_url(offline_extractor):
    assert offline_extractor.extract("http://www.example.com@evil.com/")["Abnormal_URL"] == -1.0
    assert offline_extractor.extract("http://example.com/")["Abnormal_URL"] == 1.0


def test_ssl_state_http_is_phishing_signal(offline_extractor):
    assert offline_extractor.extract("http://example.com/")["SSLfinal_State"] == -1.0


def test_dns_record_and_imputed_features(offline_extractor):
    features = offline_extractor.extract("http://example.com/")
    assert features["DNSRecord"] == 1.0
    assert features["web_traffic"] != features["web_traffic"]  # NaN
    assert features["Page_Rank"] != features["Page_Rank"]  # NaN
    assert features["Google_Index"] != features["Google_Index"]  # NaN
    assert features["Links_pointing_to_page"] != features["Links_pointing_to_page"]  # NaN
    assert features["Statistical_report"] != features["Statistical_report"]  # NaN
