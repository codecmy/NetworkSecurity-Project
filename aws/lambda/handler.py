"""AWS Lambda handler for the PhishGuard risk-scoring API.

Entry point for the container image deployed by ``aws/infrastructure``. The
model is loaded from S3 once per execution environment during cold start and
kept in memory; this handler only performs request handling and inference.

Routes (mapped by API Gateway HTTP API):
    POST /predict_url          score a single URL  (extension /predict_url)
    POST /predict_urls         score a batch of URLs
    POST /api/v1/analyze       alias of /predict_url
    POST /feedback             record user feedback (best-effort)
    POST /api/v1/feedback      alias of /feedback
    GET  /api/v1/model/version current model version / metrics
    GET  /health               liveness probe
    $default                   any other method/path -> 404 (OPTIONS -> CORS)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

_RUNTIME = None
_COLD_START = True

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-API-Key",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
}

ANALYZE_PATHS = {"/predict_url", "/api/v1/analyze"}
BATCH_PATHS = {"/predict_urls"}
FEEDBACK_PATHS = {"/feedback", "/api/v1/feedback"}
VERSION_PATHS = {"/api/v1/model/version"}
HEALTH_PATHS = {"/health"}


def _log_event(event: str, **fields: Any) -> None:
    record = {"event": event, "request_id": _REQUEST_ID}
    record.update(fields)
    logger.info(json.dumps(record, default=str))


_REQUEST_ID = None


# ------------------------------------------------------------------ runtime
def _runtime():
    global _RUNTIME, _COLD_START, _REQUEST_ID
    if _RUNTIME is None:
        bucket = os.getenv("PHISHGUARD_MODEL_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("PHISHGUARD_MODEL_BUCKET is not set")
        from networksecurity.serving.model_store import S3ModelStore
        from networksecurity.serving.runtime import ScorerRuntime

        store = S3ModelStore(bucket=bucket)
        _RUNTIME = ScorerRuntime(store)
        _log_event("runtime_initialized", bucket=bucket, cold_start=_COLD_START)
    return _RUNTIME


# ------------------------------------------------------------------- helpers
def _response(status: int, payload: Any) -> Dict:
    return {
        "statusCode": status,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _ok(payload: Any, status: int = 200) -> Dict:
    return _response(status, payload)


def _err(status: int, message: str) -> Dict:
    return _response(status, {"error": message})


def _json_body(event: Dict) -> Optional[Dict]:
    body = event.get("body")
    if not body:
        return None
    try:
        if isinstance(body, str):
            return json.loads(body)
        return body
    except (ValueError, TypeError):
        return None


def _require_api_key(event: Dict) -> Optional[Dict]:
    expected = os.getenv("PHISHGUARD_API_KEY", "").strip()
    if not expected:
        return None
    headers = event.get("headers") or {}
    provided = headers.get("x-api-key", "")
    if provided != expected:
        return _err(401, "invalid or missing X-API-Key header")
    return None


def _validate_urls(raw) -> List[str]:
    if isinstance(raw, str):
        urls = [raw]
    elif isinstance(raw, list):
        urls = raw
    else:
        raise ValueError("expected a 'url' string or 'urls' list")
    if not 1 <= len(urls) <= 100:
        raise ValueError("expected between 1 and 100 urls")
    cleaned = []
    for url in urls:
        if not isinstance(url, str) or len(url.strip()) < 3:
            raise ValueError("each url must be a non-empty string of at least 3 characters")
        cleaned.append(url.strip())
    return cleaned


# ---------------------------------------------------------------- inference
def _handle_analyze(event: Dict) -> Dict:
    start = time.perf_counter()
    body = _json_body(event) or {}
    try:
        raw = body.get("url", body.get("urls"))
        urls = _validate_urls(raw)
        single = isinstance(raw, str)
        scorer, version = _runtime().get()
        if single:
            result = scorer.score(urls[0])
            result["model_version"] = version
            payload = result
            event_name = "model_inference"
        else:
            results = scorer.score_many(urls)
            for r in results:
                r["model_version"] = version
            payload = {"results": results}
            event_name = "model_inference_batch"

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _log_event(
            event_name,
            count=len(urls),
            model_version=version,
            duration_ms=duration_ms,
            result=payload.get("label") if single else None,
            cold_start=_COLD_START,
        )
        return _ok(payload)
    except ValueError as exc:
        return _err(400, str(exc))
    except Exception as exc:
        logger.exception("inference failed")
        _log_event("model_inference_error", error=type(exc).__name__, cold_start=_COLD_START)
        return _err(502, "inference failed")


def _handle_version(event: Dict) -> Dict:
    runtime = _runtime()
    store = runtime._store
    version = runtime.version or store.version()
    manifest = store.production_manifest()
    payload = {
        "version": version,
        "model": manifest.get("model"),
        "model_full": manifest.get("model_full"),
        "preprocessor": manifest.get("preprocessor"),
        "accuracy": manifest.get("accuracy"),
        "precision": manifest.get("precision"),
        "recall": manifest.get("recall"),
        "f1": manifest.get("f1"),
        "metrics": manifest.get("metrics") or {},
        "trained_at": manifest.get("trained_at"),
        "promoted_at": manifest.get("promoted_at"),
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _log_event("model_version_queried", model_version=version)
    return _ok(payload)


# ---------------------------------------------------------------- feedback
_feedback_extractor = None


def _handle_feedback(event: Dict) -> Dict:
    body = _json_body(event) or {}
    url = body.get("url")
    if not isinstance(url, str) or len(url.strip()) < 1:
        return _err(400, "missing 'url'")

    from networksecurity.database import feedback_repository
    from networksecurity.utils.feature_extraction.extractor import PhishingFeatureExtractor

    global _feedback_extractor
    if _feedback_extractor is None:
        _feedback_extractor = PhishingFeatureExtractor(
            request_timeout=6.0, resolve_timeout=4.0, use_whois=False
        )

    features = {}
    try:
        features = _feedback_extractor.extract(url)
    except Exception:
        features = {}

    doc = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": url,
        "verdict": body.get("verdict", ""),
        "label": body.get("label", ""),
        "phishing_probability": body.get("phishing_probability"),
        "feedback": body.get("feedback", ""),
        "reason": body.get("reason", ""),
        "features": features,
    }

    try:
        doc_id = feedback_repository.save_feedback(doc)
        _log_event("feedback_saved", source="mongo", doc_id=doc_id)
        return _ok({"ok": True, "recorded": doc["timestamp"], "source": "mongo", "id": doc_id})
    except Exception:
        logger.warning("mongo feedback save failed - dropping (best-effort)", exc_info=True)
        _log_event("feedback_dropped", source="none")
        return _ok({"ok": True, "recorded": doc["timestamp"], "source": "dropped"})


# ------------------------------------------------------------------- entry
def lambda_handler(event: Dict, context: Any = None) -> Dict:
    global _COLD_START, _REQUEST_ID
    if context is not None:
        _REQUEST_ID = getattr(context, "aws_request_id", None)
    cold_start = _COLD_START
    _COLD_START = False

    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "").upper()
    path = event.get("rawPath", "")

    if method == "OPTIONS":
        return _response(200, "")

    if not (method, path):
        return _err(400, "unsupported invocation event")

    if path in HEALTH_PATHS and method == "GET":
        _log_event("health_check", cold_start=cold_start)
        return _ok({"status": "ok", "service": "network-security"})

    if path in VERSION_PATHS and method == "GET":
        try:
            return _handle_version(event)
        except Exception:
            logger.exception("version query failed")
            return _err(502, "model registry unavailable")

    auth_error = _require_api_key(event)
    if auth_error is not None:
        return auth_error

    if method == "POST" and path in ANALYZE_PATHS:
        return _handle_analyze(event)

    if method == "POST" and path in BATCH_PATHS:
        return _handle_analyze(event)

    if method == "POST" and path in FEEDBACK_PATHS:
        return _handle_feedback(event)

    _log_event("unknown_route", method=method, path=path)
    return _err(404, "not found")
