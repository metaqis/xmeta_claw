"""报告技能注册中心 — 定义 ReportSkill 协议和技能注册/获取接口。

未来新增报告类型只需：
1. 在子包中实现 ReportSkill 协议
2. 用 @register("type_name") 装饰器注册
3. 在子包 __init__.py 中导入以触发注册
"""
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class ReportSkill(Protocol):
    """每种报告类型（日/周/月）的标准接口。"""

    async def get_data(self, db: AsyncSession, **kwargs) -> dict[str, Any]:
        """获取并处理报告数据。"""
        ...

    def generate_charts(self, data: dict[str, Any], output_dir: str) -> dict[str, str]:
        """生成图表，返回 {chart_key: file_path}。"""
        ...

    def build_prompt(self, data: dict[str, Any], available_charts: list[str]) -> str:
        """构建 LLM Prompt。"""
        ...


_REGISTRY: dict[str, type] = {}


def register(name: str):
    """将实现 ReportSkill 协议的类注册到全局注册表。"""
    def decorator(cls):
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_skill(report_type: str) -> ReportSkill:
    """按名称获取报告技能实例。"""
    cls = _REGISTRY.get(report_type)
    if not cls:
        available = list(_REGISTRY.keys())
        raise ValueError(f"未知报告类型: {report_type}，可用: {available}")
    return cls()


def list_skills() -> list[str]:
    """列出所有已注册的报告类型。"""
    return list(_REGISTRY.keys())
