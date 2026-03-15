from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/jingtan"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/jingtan"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALGORITHM: str = "HS256"

    # Crawler
    CRAWLER_API_BASE: str = "https://api.x-metash.cn"
    CRAWLER_REQUEST_DELAY: float = 0.5
    CRAWLER_CONCURRENCY: int = 3  # 最大并发请求数
    CRAWLER_PROXY: str = ""  # 代理地址，如 http://user:pass@host:port

    # Admin
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
