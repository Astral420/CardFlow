from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.celery_app
from app.api import auth, batches, cards, duplicates, rotation

from app.config import settings

app = FastAPI(title="Card Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(batches.router)
app.include_router(rotation.router)
app.include_router(duplicates.router)
app.include_router(cards.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
