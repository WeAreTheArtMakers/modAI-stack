from fastapi import APIRouter, Depends, Response

from app.api.deps import require_admin
from app.services.observability import metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(user=Depends(require_admin)):
    del user
    return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
