import httpx
from fastapi import APIRouter, Request

PERFORMANCE_URL = "http://performance:5004"

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/health")
async def health():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{PERFORMANCE_URL}/health")
        return r.json()


@router.post("/project")
async def create_project(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/project", json=body)
        return r.json()


@router.post("/project/{project_id}/phases")
async def add_phases(project_id: int, request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/project/{project_id}/phases", json=body)
        return r.json()


@router.post("/progress")
async def record_progress(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/progress", json=body, timeout=60.0)
        return r.json()


@router.post("/predict")
async def predict_delay(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{PERFORMANCE_URL}/predict", json=body, timeout=60.0)
        return r.json()


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
