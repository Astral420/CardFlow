from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.celery_app
from app.api import auth, batches, cards, duplicates, rotation, users

from app.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fail loudly rather than silently accepting logins/issuing JWTs signed
    # with a secret anyone can read out of this repo's .env.example.
    insecure = settings.insecure_defaults()
    if insecure:
        names = ", ".join(insecure)
        raise RuntimeError(
            f"Refusing to start: {names} still set to the default "
            "placeholder value. Set real value(s) in .env before running "
            "the API."
        )
    yield


app = FastAPI(title="Card Tool API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(batches.router)
app.include_router(rotation.router)
app.include_router(duplicates.router)
app.include_router(cards.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
