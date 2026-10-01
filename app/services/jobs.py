import asyncio
from collections.abc import Awaitable, Callable
class JobQueue:
    """Bounded queue provides backpressure; workers are cancelled during shutdown."""
    def __init__(self, workers: int = 2, maxsize: int = 100):
        self.queue: asyncio.Queue[tuple[Callable[..., Awaitable], tuple]] = asyncio.Queue(maxsize=maxsize)
        self.workers: list[asyncio.Task] = []
        self.worker_count = workers
    async def start(self): self.workers = [asyncio.create_task(self._worker()) for _ in range(self.worker_count)]
    async def _worker(self):
        while True:
            fn, args = await self.queue.get()
            try: await fn(*args)
            finally: self.queue.task_done()
    async def submit(self, fn, *args): await self.queue.put((fn, args))
    async def stop(self):
        await self.queue.join()
        for task in self.workers: task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

