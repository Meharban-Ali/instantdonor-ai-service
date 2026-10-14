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

        Returns:
            True if loaded successfully, False if missing or corrupted.
        """
        config = get_ml_config()
        model_path = config.model_path

        if not os.path.isfile(model_path):
            self._loaded = False
            self._model = None
            self._load_error = f"Model file not found at path: {model_path}"
            logger.error(self._load_error)
            return False

        try:
            # Try joblib first, then pickle fallback
            try:
                self._model = joblib.load(model_path)
            except Exception:
                with open(model_path, "rb") as f:
                    self._model = pickle.load(f)

            self._loaded = True
            self._load_error = None
            logger.info("ML model loaded successfully from %s", model_path)
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
