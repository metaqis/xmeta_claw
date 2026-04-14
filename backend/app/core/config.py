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

    # AntFans (鲸探 App 内部网关)
    ANTFANS_API_BASE: str = "https://mgs-normal.antfans.com"
    ANTFANS_OPERATION_TYPE_QUERY_SKU_WIKI: str = (
        "com.antgroup.antchain.mymobileprod.common.service.facade.scope.social.querySkuWiki"
    )
    ANTFANS_OPERATION_TYPE_QUERY_SKU_HOMEPAGE: str = (
        "com.antgroup.antchain.mymobileprod.common.service.facade.scope.social.querySKUHomepage"
    )
    ANTFANS_SIGN_SECRET: str = ""
    ANTFANS_SIGN_TYPE: str = "0"
    ANTFANS_DID: str = "TEMP-abtToO7CtX8DAP2YUJu3pHSY"
    ANTFANS_APP_ID: str = "ALIPUB059F038311550"
    ANTFANS_WORKSPACE_ID: str = "prod"
    ANTFANS_PRODUCT_VERSION: str = "1.8.5.241219194812"
    ANTFANS_PRODUCT_ID: str = "ALIPUB059F038311550_ANDROID"
    ANTFANS_X_APP_SYS_ID: str = "com.antfans.fans"
    ANTFANS_EXTRA_HEADERS: dict[str, str] = {
        "x-source": "fans",
        "x-platform": "Android",
        "Accept-Language": "zh-Hans",
    }
    ANTFANS_CONCURRENCY: int = 1
    ANTFANS_REQUEST_DELAY: float = 1.0
    ANTFANS_REQUEST_DELAY_JITTER_RATIO: float = 0.4

    # LLM (qwen-plus via DashScope OpenAI-compatible API)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "qwen-plus"
    LLM_MAX_TOKENS: int = 6144
    LLM_TEMPERATURE: float = 0.2
    AGENT_MAX_HISTORY: int = 16
    AGENT_MAX_TOOL_ROUNDS: int = 5

    # WeChat Mini Program (微信小程序，已有配置)
    APP_ID: str = ""
    APP_SECRET: str = ""

    # WeChat MP (微信公众号)
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    # Admin
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # 微信公众号（文章自动发布）
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
