from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import CORS_ORIGINS
from .routes.auth import auth_router
from .routes.checkin import checkin_router
from .routes.feedback import feedback_router
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

    app.include_router(auth_router, tags=["auth"])
    app.include_router(checkin_router, tags=["checkin"])
    app.include_router(feedback_router, tags=["feedback"])
    app.include_router(meeting_router, tags=["meeting"])
    app.include_router(post_router, tags=["post"])

    return app


app = get_application()
