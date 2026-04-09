"""日报技能 — 注册 DailyReportSkill 到全局注册表。"""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.article.reports import register
from .analyzer import get_daily_data
from .charts import generate_daily_charts
from .prompt import build_daily_prompt


@register("daily")
class DailyReportSkill:
    async def get_data(self, db: AsyncSession, **kwargs) -> dict[str, Any]:
        target_date: str = kwargs["target_date"]
        return await get_daily_data(db, target_date)

    def generate_charts(self, data: dict[str, Any], output_dir: str) -> dict[str, str]:
        return generate_daily_charts(data, output_dir)

    def build_prompt(self, data: dict[str, Any], available_charts: list[str]) -> str:
        return build_daily_prompt(data, available_charts)
