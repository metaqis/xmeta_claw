from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE IF EXISTS ips ADD COLUMN IF NOT EXISTS source_uid INTEGER"))
        await conn.execute(text("ALTER TABLE IF EXISTS ips ADD COLUMN IF NOT EXISTS from_type INTEGER DEFAULT 1"))
        await conn.execute(text("ALTER TABLE IF EXISTS ips ADD COLUMN IF NOT EXISTS description TEXT"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_ips_source_uid ON ips (source_uid) WHERE source_uid IS NOT NULL"))
        await conn.execute(text("ALTER TABLE IF EXISTS archives ADD COLUMN IF NOT EXISTS total_goods_count INTEGER"))
