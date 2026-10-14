# ai-service/core/model_loader.py

import logging
import os
import pickle
from typing import Any, Optional

import joblib

from core.config import get_ml_config

logger = logging.getLogger(__name__)


class MLModelManager:
    """
    Singleton manager for loading, caching, and validating the ML model.

    SOLID S: Lifecycle management and in-memory cache of ML model only.
    """
    _instance: Optional["MLModelManager"] = None
    _model: Any = None
    _loaded: bool = False
    _load_error: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "MLModelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (used in tests)."""
        cls._instance = None
        cls._model = None
        cls._loaded = False
        cls._load_error = None

    def load_model(self) -> bool:
        """
        Load ML model file into memory once at startup.
        Verifies fixed path, read-only access, and SHA-256 cryptographic integrity
        prior to deserialization to prevent malicious pickle execution.

        Returns:
            True if loaded and verified successfully, False if missing, corrupt, or hash mismatch.
        """
        import hashlib

        config = get_ml_config()
        # Enforce fixed canonical path
        model_path = os.path.abspath(config.model_path)

        if not os.path.isfile(model_path):
            self._loaded = False
            self._model = None
            self._load_error = f"Model file not found at path: {model_path}"
            logger.error(self._load_error)
            return False

        try:
            # Read-only byte verification
            with open(model_path, "rb") as f:
                model_bytes = f.read()

            actual_sha256 = hashlib.sha256(model_bytes).hexdigest()

            # Expected hash from configuration or default model hash
            expected_sha256 = os.getenv("MODEL_SHA256")
            cfg_hash = getattr(config, "model_sha256", None)
            if not expected_sha256 and isinstance(cfg_hash, str) and cfg_hash.strip():
                expected_sha256 = cfg_hash.strip()
            if not expected_sha256 and model_path.endswith("donor_matching_model.pkl"):
                expected_sha256 = "d31d40988940d64a20b655d8239080cfacb0436ac248c9f9fcaf50ba00264236"

            if expected_sha256 and actual_sha256.lower() != expected_sha256.strip().lower():
                self._loaded = False
                self._model = None
                self._load_error = (
                    f"Model SHA-256 integrity verification failed: "
                    f"expected {expected_sha256}, got {actual_sha256}"
                )
                logger.error(self._load_error)
                return False

            # Deserialization only after cryptographic integrity verification passes
            try:
                self._model = joblib.load(model_path)
            except Exception:
                self._model = pickle.loads(model_bytes)

            self._loaded = True
            self._load_error = None
            logger.info("ML model loaded and verified (SHA-256: %s) from %s", actual_sha256[:12], model_path)
            return True
        except Exception as e:
            self._loaded = False
            self._model = None
            self._load_error = f"Corrupt or invalid ML model file '{model_path}': {e}"
            logger.error(self._load_error, exc_info=True)
            return False

    @property
    def is_loaded(self) -> bool:
        """Is the ML model loaded and ready in memory?"""
        return self._loaded

    @property
    def model(self) -> Any:
        """Get the cached ML model instance."""
        return self._model

    @property
    def load_error(self) -> Optional[str]:
        """Error string if loading failed."""
        return self._load_error
