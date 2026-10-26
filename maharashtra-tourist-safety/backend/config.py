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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
