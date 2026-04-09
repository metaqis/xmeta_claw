"""月报技能 — 注册 MonthlyReportSkill 到全局注册表。"""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.article.reports import register
from .analyzer import get_monthly_data
from .charts import generate_monthly_charts
from .prompt import build_monthly_prompt


@register("monthly")
class MonthlyReportSkill:
    async def get_data(self, db: AsyncSession, **kwargs) -> dict[str, Any]:
        year: int  = int(kwargs["year"])
        month: int = int(kwargs["month"])
        return await get_monthly_data(db, year, month)

    def generate_charts(self, data: dict[str, Any], output_dir: str) -> dict[str, str]:
        return generate_monthly_charts(data, output_dir)

    def build_prompt(self, data: dict[str, Any], available_charts: list[str]) -> str:
        return build_monthly_prompt(data, available_charts)
