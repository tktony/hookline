from fastapi import APIRouter

router = APIRouter()

# Uptime health Check
@router.get("/health")
def health():
    return {"status": "ok"}
