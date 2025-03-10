from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import CORS_ORIGINS
from .routes.auth import auth_router
from .routes.meeting import meeting_router
from .routes.post import post_router


def get_application():
    app = FastAPI(
        title="SoarHigh Toastmasters Club API",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth_router)
    app.include_router(meeting_router)
    app.include_router(post_router)

    return app


app = get_application()
