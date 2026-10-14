import os
import warnings
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ─────────────────────────────────────────────────────────
# ✅ S: Sirf AI weights config ka kaam
# ✅ O: Naya weight = yahan add karo — Settings change nahi
# ✅ D: Field validators — hardcode nahi
# ─────────────────────────────────────────────────────────
class AIWeightsConfig(BaseSettings):
    """
    AI donor matching scoring weights.

    Formula:
        score = (distance    × 0.40)
              + (reliability × 0.30)
              + (eligibility × 0.20)
              + (response    × 0.10)
              = 1.00 ✅

    All weights MUST sum to exactly 1.0!
    """

    weight_distance: float = Field(
        default=0.40,
        ge=0.0, le=1.0,
        description="Distance weight (0-1) — 40% default"
    )
    weight_reliability: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description="Reliability score weight (0-1) — 30% default"
    )
    weight_eligibility: float = Field(
        default=0.20,
        ge=0.0, le=1.0,
        description="Eligibility weight (0-1) — 20% default"
    )
    weight_response_rate: float = Field(
        default=0.10,
        ge=0.0, le=1.0,
        description="Response rate weight (0-1) — 10% default"
    )

    @model_validator(mode='after')
    def validate_weights_sum(self) -> 'AIWeightsConfig':
        total = (
                self.weight_distance    +
                self.weight_reliability +
                self.weight_eligibility +
                self.weight_response_rate
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"AI weights must sum to 1.0, got {total:.4f}.\n"
                f"  distance={self.weight_distance}\n"
                f"  reliability={self.weight_reliability}\n"
                f"  eligibility={self.weight_eligibility}\n"
                f"  response_rate={self.weight_response_rate}\n"
                f"  total={total:.4f} ← Must be 1.0"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)  # ✅ Fix Pydantic warning
    )


# ─────────────────────────────────────────────────────────
# ✅ Database Config
# ─────────────────────────────────────────────────────────
class DatabaseConfig(BaseSettings):
    """
    MySQL Database configuration.

    Spring Boot wali DB use karta hai — read-only access.
    Connection pool manage karta hai — high performance.
    """

    db_url: str = Field(
        default="",
        description=(
            "MySQL connection URL. Set DB_URL in .env\n"
            "Format: mysql+pymysql://user:pass@host:port/db"
        )
    )
    db_pool_size: int     = Field(
        default=5, ge=1, le=20,
        description="Connection pool size"
    )
    db_max_overflow: int  = Field(
        default=10, ge=0, le=50,
        description="Max overflow connections"
    )
    db_pool_timeout: int  = Field(
        default=30, ge=5, le=120,
        description="Pool checkout timeout seconds"
    )
    db_pool_recycle: int  = Field(
        default=1800, ge=300,
        description="Connection recycle seconds (30 min)"
    )
    db_pool_pre_ping: bool = Field(
        default=True,
        description="Check connection health before use"
    )
    db_echo: bool = Field(
        default=False,
        description="Log SQL queries — True only in dev!"
    )

    @field_validator('db_url')
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v:
            warnings.warn(
                "DB_URL is empty! "
                "Set DB_URL in .env file.\n"
                "Format: mysql+pymysql://user:pass@host:port/db",
                UserWarning,
                stacklevel=2
            )
            return v

        valid_prefixes = (
            'mysql+pymysql://',
            'mysql+aiomysql://',
            'postgresql+psycopg2://',
            'postgresql+asyncpg://',
            'sqlite:///',
        )
        if not any(v.startswith(p) for p in valid_prefixes):
            raise ValueError(
                f"Invalid DB URL format!\n"
                f"Got: {v[:30]}...\n"
                f"Must start with one of:\n"
                f"  {chr(10).join(valid_prefixes)}"
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)
    )


# ─────────────────────────────────────────────────────────
# ✅ Redis Config
# ─────────────────────────────────────────────────────────
class RedisConfig(BaseSettings):
    """
    Redis Cache configuration.

    Cache TTL settings:
        donor_search → 5 min (300s)
        prediction   → 10 min (600s)
        model        → 1 hour (3600s)
    """

    redis_host: str = Field(
        default="localhost",
        description="Redis server hostname"
    )
    redis_port: int = Field(
        default=6379, ge=1, le=65535,
        description="Redis server port"
    )
    redis_password: str = Field(
        default="",
        description="Redis password (empty = no auth)"
    )
    redis_db: int = Field(
        default=0, ge=0, le=15,
        description="Redis DB number (0-15)"
    )
    redis_ssl: bool = Field(
        default=False,
        description="Use SSL/TLS for Redis (True in production)"
    )
    redis_ttl_donor_search: int = Field(
        default=300, ge=1,
        description="Donor search results TTL (5 min)"
    )
    redis_ttl_prediction: int = Field(
        default=600, ge=1,
        description="Demand prediction results TTL (10 min)"
    )
    redis_ttl_model: int = Field(
        default=3600, ge=1,
        description="ML model cache TTL (1 hour)"
    )

    @property
    def redis_url(self) -> str:
        """Redis connection URL build karo."""
        scheme = "rediss" if self.redis_ssl else "redis"

        if self.redis_password:
            return (
                f"{scheme}://:{self.redis_password}"
                f"@{self.redis_host}:{self.redis_port}"
                f"/{self.redis_db}"
            )
        return (
            f"{scheme}://{self.redis_host}"
            f":{self.redis_port}"
            f"/{self.redis_db}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)
    )


# ─────────────────────────────────────────────────────────
# ✅ Security Config - UPDATED with better CORS parsing
# ─────────────────────────────────────────────────────────
class SecurityConfig(BaseSettings):
    """
    Security configuration with robust CORS parsing.

    Supports multiple CORS formats:
        - "http://localhost:8080,http://localhost:3000"
        - '["http://localhost:8080", "http://localhost:3000"]'
        - ["http://localhost:8080", "http://localhost:3000"]
    """

    jwt_secret: str = Field(
        default="BloodDonorNetworkSecretKey2024ForLocalDevOnly123456",
        description="JWT secret key (min 32 chars)"
    )
    jwt_algorithm: str = Field(
        default="HS384",
        description="JWT algorithm: HS256, HS384, HS512"
    )
    cors_origins: List[str] = Field(
        default=["http://localhost:8080", "http://localhost:3000", "http://localhost:5173"],
        description="CORS allowed origins"
    )
    api_key: str = Field(
        default="local-dev-api-key-change-in-production",
        description="Internal service API key"
    )

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """
        Universal CORS parser - handles ALL formats.

        Supports:
            - None / "" → default list
            - "url1,url2,url3" → comma-separated
            - '["url1", "url2"]' → JSON array
            - ["url1", "url2"] → already list
            - "url1" → single origin
        """
        import json as _json

        # Default fallback
        default_origins = ["http://localhost:8080", "http://localhost:3000", "http://localhost:5173"]

        # Handle None or empty
        if v is None or v == "":
            return default_origins

        # Already a list
        if isinstance(v, list):
            cleaned = [str(o).strip() for o in v if str(o).strip()]
            return cleaned if cleaned else default_origins

        # String processing
        if isinstance(v, str):
            v = v.strip()

            # Empty string
            if not v:
                return default_origins

            # Try JSON array format first
            if v.startswith('['):
                try:
                    parsed = _json.loads(v)
                    if isinstance(parsed, list):
                        cleaned = [str(o).strip() for o in parsed if str(o).strip()]
                        if cleaned:
                            return cleaned
                except _json.JSONDecodeError:
                    pass  # Fall through to comma split

            # Try comma-separated format
            if ',' in v:
                origins = [o.strip() for o in v.split(',') if o.strip()]
                if origins:
                    return origins

            # Single origin
            return [v]

        # Unknown type - return default
        return default_origins

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError(f"JWT secret must be >= 32 chars, got {len(v)}")
        if not v:
            warnings.warn("JWT_SECRET is empty! This is insecure!", UserWarning, stacklevel=2)
        return v

    @field_validator('jwt_algorithm')
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        allowed = {'HS256', 'HS384', 'HS512'}
        if v not in allowed:
            raise ValueError(f"JWT algorithm must be one of {allowed}, got '{v}'")
        return v

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v:
            warnings.warn("API_KEY is empty! This is insecure!", UserWarning, stacklevel=2)
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)  # ✅ Fix Pydantic warning
    )


# ─────────────────────────────────────────────────────────
# ✅ ML Config - Fixed with protected_namespaces
# ─────────────────────────────────────────────────────────
class MLConfig(BaseSettings):
    """
    ML Model configuration.

    Model path auto-resolves to absolute path.
    Check model_exists before loading!
    """

    model_path: str = Field(
        default="models/donor_matching_model.pkl",
        description="Path to trained ML model (.pkl)"
    )
    model_version: str = Field(
        default="1.0.0",
        description="Model version — for tracking"
    )
    max_donors_result: int = Field(
        default=10, ge=1, le=100,
        description="Max donors to return in results"
    )
    default_radius_km: float = Field(
        default=50.0, gt=0, le=500,
        description="Default search radius in km"
    )
    max_radius_km: float = Field(
        default=100.0, gt=0, le=1000,
        description="Maximum allowed search radius"
    )
    min_samples_for_retrain: int = Field(
        default=100, ge=10,
        description="Minimum samples before model retrain"
    )

    # Internal fields - to track model state
    model_loaded: bool = Field(
        default=False,
        description="Is model currently loaded in memory?"
    )

    @field_validator('model_path')
    @classmethod
    def resolve_model_path(cls, v: str) -> str:
        """Convert relative path to absolute path."""
        if not os.path.isabs(v):
            # core/config.py → core/ → ai-service/
            base_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            return os.path.join(base_dir, v)
        return v

    @property
    def model_exists(self) -> bool:
        """Check if model file exists."""
        return os.path.isfile(self.model_path)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)  # ✅ Fix for model_* fields warning
    )


# ─────────────────────────────────────────────────────────
# ✅ Main Settings
# ─────────────────────────────────────────────────────────
class Settings(BaseSettings):
    """
    Main application settings.

    App-level config only:
        app_name, version, debug, environment
        host, port, spring_boot_url

    DB/Redis/ML/Security → alag config classes
    """

    app_name: str = Field(
        default="Blood Donor AI Service",
        description="Application name"
    )
    app_version: str = Field(
        default="1.0.0",
        description="Application version"
    )
    debug: bool = Field(
        default=False,
        description="Debug mode — NEVER true in production!"
    )
    environment: str = Field(
        default="development",
        description="Environment: development | staging | production"
    )
    host: str = Field(
        default="0.0.0.0",
        description="Server host"
    )
    port: int = Field(
        default=8000, ge=1, le=65535,
        description="Server port"
    )
    spring_boot_url: str = Field(
        default="http://localhost:8080",
        description="Spring Boot backend URL"
    )

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Environment validate karo."""
        allowed = {'development', 'staging', 'production'}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(
                f"Invalid environment: '{v}'.\n"
                f"Must be one of: {allowed}"
            )
        return v

    @model_validator(mode='after')
    def validate_production_settings(self) -> 'Settings':
        """Production safety checks."""
        if self.environment == 'production' and self.debug:
            raise ValueError(
                "DEBUG cannot be True in production!\n"
                "Set DEBUG=false in .env"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == 'production'

    @property
    def is_development(self) -> bool:
        return self.environment == 'development'

    @property
    def is_staging(self) -> bool:
        return self.environment == 'staging'

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)
    )


# ─────────────────────────────────────────────────────────
# ✅ Singleton cached instances
# ─────────────────────────────────────────────────────────

@lru_cache()
def get_settings() -> Settings:
    """Main app settings — cached singleton."""
    return Settings()


@lru_cache()
def get_db_config() -> DatabaseConfig:
    """Database config — cached singleton."""
    return DatabaseConfig()


@lru_cache()
def get_redis_config() -> RedisConfig:
    """Redis config — cached singleton."""
    return RedisConfig()


@lru_cache()
def get_security_config() -> SecurityConfig:
    """Security config — cached singleton."""
    return SecurityConfig()


@lru_cache()
def get_ml_config() -> MLConfig:
    """ML model config — cached singleton."""
    return MLConfig()


@lru_cache()
def get_ai_weights() -> AIWeightsConfig:
    """AI scoring weights — cached singleton."""
    return AIWeightsConfig()


def clear_settings_cache() -> None:
    """Clear all config caches (useful for testing)."""
    get_settings.cache_clear()
    get_db_config.cache_clear()
    get_redis_config.cache_clear()
    get_security_config.cache_clear()
    get_ml_config.cache_clear()
    get_ai_weights.cache_clear()