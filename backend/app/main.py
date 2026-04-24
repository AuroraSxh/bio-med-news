from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.routes import router
from app.core.logging import setup_logging
from app.services.database_init import init_database

limiter = Limiter(key_func=get_remote_address)
setup_logging()

app = FastAPI(
    title="Biomed / Cell Therapy Daily Intelligence API",
    version="0.5.0",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("startup")
def startup() -> None:
    init_database()


app.include_router(router)
