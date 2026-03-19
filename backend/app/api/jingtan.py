from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import require_admin
from app.core.config import get_settings
from app.crawler.antfans_client import antfans_client

settings = get_settings()

router = APIRouter(prefix="/jingtan", tags=["鲸探"])


class SkuWikiListQuery(BaseModel):
    pageNum: int = 1
    pageSize: int = 20


class AntFansProxyResponse(BaseModel):
    status: int
    data: Optional[Any] = None
    text: str = ""


@router.post("/sku-wiki-list", response_model=AntFansProxyResponse)
async def sku_wiki_list(
    req: list[SkuWikiListQuery],
    _admin=Depends(require_admin),
):
    payload_obj = [req[0].model_dump()] if req else [{"pageNum": 1, "pageSize": 20}]
    result = await antfans_client.post_mgw_safe(
        operation_type=settings.ANTFANS_OPERATION_TYPE_QUERY_SKU_WIKI,
        payload_obj=payload_obj,
    )
    return AntFansProxyResponse(status=result["status"], data=result["json"], text=result["text"])
