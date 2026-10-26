from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # MongoDB
    MONGO_URI: str = Field(default="mongodb://localhost:27017", env="MONGO_URI")
    MONGO_DB_NAME: str = Field(default="maharashtra_tourist_safety", env="MONGO_DB_NAME")

    # Firebase
    FIREBASE_CREDENTIALS_PATH: str = Field(default="firebase-credentials.json", env="FIREBASE_CREDENTIALS_PATH")

    # JWT
    JWT_SECRET: str = Field(default="change-me-in-production", env="JWT_SECRET")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_EXPIRE_HOURS: int = Field(default=8, env="JWT_EXPIRE_HOURS")

    # Blockchain / Ganache
    GANACHE_URL: str = Field(default="http://127.0.0.1:7545", env="GANACHE_URL")
    CONTRACT_ADDRESS: str = Field(default="", env="CONTRACT_ADDRESS")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")

    # API
    API_V1_PREFIX: str = Field(default="/api/v1", env="API_V1_PREFIX")

    # Movement Anomaly Detection
    ANOMALY_STATIONARY_DIST_M: float = Field(default=10.0, env="ANOMALY_STATIONARY_DIST_M")
    ANOMALY_STATIONARY_WINDOW_MS: int = Field(default=600_000, env="ANOMALY_STATIONARY_WINDOW_MS")
    ANOMALY_SPEED_MS: float = Field(default=30.0, env="ANOMALY_SPEED_MS")
    ANOMALY_GPS_LOSS_TIMEOUT_MS: int = Field(default=300_000, env="ANOMALY_GPS_LOSS_TIMEOUT_MS")
    ANOMALY_ROUTE_DEVIATION_M: float = Field(default=500.0, env="ANOMALY_ROUTE_DEVIATION_M")
    ANOMALY_DIRECTION_CHANGE_DEG: float = Field(default=120.0, env="ANOMALY_DIRECTION_CHANGE_DEG")
    ANOMALY_MIN_POINTS: int = Field(default=3, env="ANOMALY_MIN_POINTS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
