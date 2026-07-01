from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    database_url: str = "postgresql+psycopg://social:social@postgres:5432/social"

    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "social_chat"

    redis_url: str = "redis://redis:6379/0"

    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_chat_topic: str = "chat.messages"
    kafka_events_topic: str = "social.events"
    kafka_consumer_group: str = "social-app"

    minio_endpoint: str = "minio:9000"
    minio_public_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "media"
    minio_secure: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    sentry_dsn: str = ""  # leave empty to disable Sentry entirely

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
