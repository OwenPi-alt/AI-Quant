import asyncio
import logging
import signal

import uvicorn
from fastapi import FastAPI

from app.settings import get_settings
from app.workers.runner import run_role

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("aiq.worker")

app = FastAPI(title="AI-Quant Worker")


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {"status": "UP", "role": settings.worker_role}


async def serve() -> None:
    settings = get_settings()
    loop = asyncio.get_running_loop()
    worker_task = asyncio.create_task(run_role(settings.worker_role, settings), name="worker")

    config = uvicorn.Config(app, host="0.0.0.0", port=8090, log_level="info")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve(), name="uvicorn")

    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    stop_task = asyncio.create_task(stop_event.wait(), name="stop")
    try:
        done, _ = await asyncio.wait(
            {worker_task, serve_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            if task is stop_task:
                continue
            if task.exception():
                logger.error("task %s failed", task.get_name(), exc_info=task.exception())
    finally:
        logger.info("shutting down")
        server.should_exit = True
        worker_task.cancel()
        for task in (worker_task, serve_task):
            try:
                await asyncio.wait_for(task, timeout=15)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                logger.exception("task %s shutdown error", task.get_name())
        stop_task.cancel()


if __name__ == "__main__":
    asyncio.run(serve())
