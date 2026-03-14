"""FastAPI 主入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.database.db import init_db, async_session
from app.database.models import User
from app.api import auth, calendar, archives, ips, stats, crawler, tasks
from app.scheduler.tasks import start_scheduler, stop_scheduler

settings = get_settings()


async def _ensure_admin():
    """确保管理员账户存在"""
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        if not result.scalar_one_or_none():
            admin = User(
                username=settings.ADMIN_USERNAME,
                password_hash=get_password_hash(settings.ADMIN_PASSWORD),
                role="admin",
            )
            db.add(admin)
            await db.commit()
            logger.info(f"管理员账户已创建: {settings.ADMIN_USERNAME}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动 JingTan Data Platform...")
    await init_db()
    await _ensure_admin()
    await start_scheduler()
    yield
    stop_scheduler()
    logger.info("已关闭")


app = FastAPI(
    title="JingTan Data Platform",
    description="鲸探数据采集与分析平台 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(archives.router)
app.include_router(ips.router)
app.include_router(stats.router)
app.include_router(crawler.router)
app.include_router(tasks.router)


@app.get("/")
async def root():
    return {"message": "JingTan Data Platform API", "version": "1.0.0"}
