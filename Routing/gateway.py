from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import from the same package (backend)
from . import web_api
from . import routing_api
from . import ble_adapter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start routing loop on startup
    await routing_api.start_routing_loop()
    yield


app: FastAPI = FastAPI(lifespan=lifespan)

# 1) Include routers FIRST so /v1/router/... and /v1/ble/... work
app.include_router(routing_api.router)
app.include_router(ble_adapter.router)

# 2) Then mount the web UI at "/"
app.mount("/", web_api.app)

# 3) CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
