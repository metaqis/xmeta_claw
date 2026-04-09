"""周报技能 — 注册 WeeklyReportSkill 到全局注册表。"""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.article.reports import register
from .analyzer import get_weekly_data
from .charts import generate_weekly_charts
from .prompt import build_weekly_prompt


@register("weekly")
class WeeklyReportSkill:
    async def get_data(self, db: AsyncSession, **kwargs) -> dict[str, Any]:
        end_date: str | None = kwargs.get("end_date")
        return await get_weekly_data(db, end_date)

    def generate_charts(self, data: dict[str, Any], output_dir: str) -> dict[str, str]:
        return generate_weekly_charts(data, output_dir)

    def build_prompt(self, data: dict[str, Any], available_charts: list[str]) -> str:
        return build_weekly_prompt(data, available_charts)
