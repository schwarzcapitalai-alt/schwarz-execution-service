from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {
        "service": "execution_service",
        "status": "healthy",
    }
