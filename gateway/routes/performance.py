import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

PERFORMANCE_URL = "http://performance:5004"

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/health")
async def health():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{PERFORMANCE_URL}/health")
        return r.json()


@router.post("/schedule")
async def post_schedule(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/schedule", json=body, timeout=30.0)
        try:
            payload = r.json()
        except ValueError:
            payload = {"success": False, "error": r.text}
        return JSONResponse(status_code=r.status_code, content=payload)


@router.post("/progress/spi")
async def post_progress_spi(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/progress/spi", json=body, timeout=30.0)
        try:
            payload = r.json()
        except ValueError:
            payload = {"success": False, "error": r.text}
        return JSONResponse(status_code=r.status_code, content=payload)


@router.post("/progress/predict")
async def post_progress_predict(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/progress/predict", json=body, timeout=60.0)
        try:
            payload = r.json()
        except ValueError:
            payload = {"success": False, "error": r.text}
        return JSONResponse(status_code=r.status_code, content=payload)


@router.get("/project/{project_id}/dashboard")
async def get_dashboard(project_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{PERFORMANCE_URL}/project/{project_id}/dashboard")
        return r.json()


@router.get("/project/{project_id}/alerts")
async def get_alerts(project_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{PERFORMANCE_URL}/project/{project_id}/alerts")
        return r.json()
