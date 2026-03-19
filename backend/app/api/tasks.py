from datetime import datetime
from typing import Optional

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.database.db import get_db
from app.database.models import TaskConfig, TaskRun, TaskRunLog
from app.scheduler.tasks import (
    TASK_DEFINITIONS,
    apply_task_config,
    cancel_task_run,
    create_task_run,
    ensure_task_configs,
    run_task_by_run_id,
    scheduler,
)

router = APIRouter(prefix="/tasks", tags=["任务管理"])


class TaskRunItem(BaseModel):
    id: int
    task_id: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class TaskItem(BaseModel):
    task_id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    schedule_type: str
    interval_seconds: Optional[int] = None
    cron: Optional[str] = None
    next_run_time: Optional[datetime] = None
    last_run: Optional[TaskRunItem] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: list[TaskItem]


class TaskUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    schedule_type: Optional[str] = None
    interval_seconds: Optional[int] = None
    cron: Optional[str] = None


class TaskUpdateResponse(BaseModel):
    message: str
    task: TaskItem


class TaskRunResponse(BaseModel):
    message: str
    run_id: int


class TaskCancelResponse(BaseModel):
    message: str


class TaskRunsResponse(BaseModel):
    total: int
    items: list[TaskRunItem]


class TaskRunLogItem(BaseModel):
    id: int
    run_id: int
    level: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class TaskRunLogsResponse(BaseModel):
    total: int
    items: list[TaskRunLogItem]


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    await ensure_task_configs()
    result = await db.execute(select(TaskConfig).order_by(TaskConfig.task_id.asc()))
    configs = [c for c in result.scalars().all() if c.task_id in TASK_DEFINITIONS]
    for cfg in configs:
        if not scheduler.get_job(cfg.task_id):
            try:
                await apply_task_config(cfg.task_id)
            except Exception:
                pass

    items: list[TaskItem] = []
    for cfg in configs:
        job = scheduler.get_job(cfg.task_id)
        next_run_time = job.next_run_time if job else None

        last_result = await db.execute(
            select(TaskRun)
            .where(TaskRun.task_id == cfg.task_id)
            .order_by(TaskRun.started_at.desc())
            .limit(1)
        )
        last_run = last_result.scalar_one_or_none()

        items.append(
            TaskItem(
                task_id=cfg.task_id,
                name=cfg.name,
                description=cfg.description,
                enabled=cfg.enabled,
                schedule_type=cfg.schedule_type,
                interval_seconds=cfg.interval_seconds,
                cron=cfg.cron,
                next_run_time=next_run_time,
                last_run=TaskRunItem.model_validate(last_run) if last_run else None,
            )
        )

    return TaskListResponse(items=items)


@router.put("/{task_id}", response_model=TaskUpdateResponse)
async def update_task(
    task_id: str,
    req: TaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    if task_id not in TASK_DEFINITIONS:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = await db.execute(select(TaskConfig).where(TaskConfig.task_id == task_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="任务不存在")

    if req.enabled is not None:
        cfg.enabled = req.enabled
    if req.schedule_type is not None:
        if req.schedule_type not in ("interval", "cron"):
            raise HTTPException(status_code=400, detail="schedule_type 必须为 interval 或 cron")
        cfg.schedule_type = req.schedule_type

    if req.interval_seconds is not None:
        if req.interval_seconds <= 0:
            raise HTTPException(status_code=400, detail="interval_seconds 必须为正数")
        cfg.interval_seconds = req.interval_seconds
    if req.cron is not None:
        cfg.cron = req.cron

    if cfg.schedule_type == "interval" and not cfg.interval_seconds:
        raise HTTPException(status_code=400, detail="interval_seconds 不能为空")
    if cfg.schedule_type == "cron" and not cfg.cron:
        raise HTTPException(status_code=400, detail="cron 不能为空")

    db.add(cfg)
    await db.commit()

    try:
        await apply_task_config(task_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    job = scheduler.get_job(task_id)
    next_run_time = job.next_run_time if job else None
    item = TaskItem(
        task_id=cfg.task_id,
        name=cfg.name,
        description=cfg.description,
        enabled=cfg.enabled,
        schedule_type=cfg.schedule_type,
        interval_seconds=cfg.interval_seconds,
        cron=cfg.cron,
        next_run_time=next_run_time,
        last_run=None,
    )
    return TaskUpdateResponse(message="任务配置已更新", task=item)


@router.post("/{task_id}/run", response_model=TaskRunResponse)
async def run_task_now(
    task_id: str,
    _admin=Depends(require_admin),
):
    if task_id not in TASK_DEFINITIONS:
        raise HTTPException(status_code=404, detail="任务不存在")

    run_id = await create_task_run(task_id)
    asyncio.create_task(run_task_by_run_id(task_id, run_id))
    return TaskRunResponse(message="任务已触发", run_id=run_id)


@router.post("/{task_id}/runs/{run_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(
    task_id: str,
    run_id: int,
    _admin=Depends(require_admin),
):
    if task_id not in TASK_DEFINITIONS:
        raise HTTPException(status_code=404, detail="任务不存在")

    ok = await cancel_task_run(task_id, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="运行记录不存在或不可停止")
    return TaskCancelResponse(message="已请求停止")


@router.get("/{task_id}/runs", response_model=TaskRunsResponse)
async def list_task_runs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    if task_id not in TASK_DEFINITIONS:
        raise HTTPException(status_code=404, detail="任务不存在")

    total_result = await db.execute(
        select(func.count(TaskRun.id)).where(TaskRun.task_id == task_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(TaskRun)
        .where(TaskRun.task_id == task_id)
        .order_by(TaskRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    runs = result.scalars().all()
    return TaskRunsResponse(total=total, items=[TaskRunItem.model_validate(r) for r in runs])


@router.get("/{task_id}/runs/{run_id}/logs", response_model=TaskRunLogsResponse)
async def list_task_run_logs(
    task_id: str,
    run_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    if task_id not in TASK_DEFINITIONS:
        raise HTTPException(status_code=404, detail="任务不存在")

    run = await db.get(TaskRun, run_id)
    if not run or run.task_id != task_id:
        raise HTTPException(status_code=404, detail="运行记录不存在")

    total_result = await db.execute(
        select(func.count(TaskRunLog.id)).where(TaskRunLog.run_id == run_id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(TaskRunLog)
        .where(TaskRunLog.run_id == run_id)
        .order_by(TaskRunLog.created_at.asc(), TaskRunLog.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()
    return TaskRunLogsResponse(total=total, items=[TaskRunLogItem.model_validate(x) for x in logs])
