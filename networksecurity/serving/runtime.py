"""Runtime bootstrap: point the scorer at artifacts fetched from S3.

The scorer is loaded once per execution environment during cold start and kept
in memory; the handler only performs inference work. See the deployment spec
section on Lambda cold start strategy.
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
from typing import Optional, Tuple

from networksecurity.serving.model_store import S3ModelStore
from networksecurity.utils.feature_extraction.scorer import UrlScorer

logger = logging.getLogger("networksecurity.serving")


class ScorerRuntime:
    """Thread-safe holder for the in-memory scorer + its model version."""

    def __init__(self, store: S3ModelStore) -> None:
        self._store = store
        self._version: Optional[str] = None
        self._scorer: Optional[UrlScorer] = None
        self._lock = threading.Lock()

    @property
    def version(self) -> Optional[str]:
        return self._version

    def get(self) -> Tuple[UrlScorer, str]:
        """Return ``(scorer, version)``, bootstrapping the model on first call."""
        with self._lock:
            if self._scorer is not None and self._version is not None:
                return self._scorer, self._version

            version = self._store.version()
            local_dir = self._store.ensure_artifacts(version)

            os.environ["PHISHGUARD_MODEL_DIR"] = local_dir
            scorer_module = importlib.import_module(
                "networksecurity.utils.feature_extraction.scorer"
            )
            scorer_module._SCORER = None  # force a fresh singleton build
            self._scorer = scorer_module.get_scorer()
            self._version = version

            logger.info("model runtime ready: version=%s dir=%s", version, local_dir)
            return self._scorer, self._version
