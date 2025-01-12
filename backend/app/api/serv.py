from fastapi import FastAPI

# from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes.auth import auth_router


def get_application():
    app = FastAPI(
        title="SoarHigh Toastmasters Club API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        # CORSMiddleware, # handled by nginx
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth_router)

    return app


app = get_application()
