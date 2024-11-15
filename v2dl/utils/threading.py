import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable, List, Optional


@dataclass
class ThreadJob:
    """Task container."""

    task_id: str
    func: Callable[..., Any]
    args: tuple
    kwargs: dict


class ThreadingService:
    """Service for processing tasks with multiple workers."""

    def __init__(self, logger: logging.Logger, num_workers: int = 1):
        self.task_queue: Queue[Optional[ThreadJob]] = Queue()
        self.logger = logger
        self.num_workers = num_workers
        self.worker_threads: list[threading.Thread] = []
        self.results: dict[str, Any] = {}
        self._lock = threading.Lock()

    def start_workers(self):
        """Start up multiple worker threads to listen for tasks."""
        for _ in range(self.num_workers):
            worker = threading.Thread(target=self._task_worker, daemon=True)
            self.worker_threads.append(worker)
            worker.start()

    def _task_worker(self):
        """Worker function to process tasks from the queue."""
        while True:
            task = self.task_queue.get()
            if task is None:
                break  # exit signal received

            try:
                result: Any = task.func(*task.args, **task.kwargs)
                with self._lock:
                    self.results[task.task_id] = result
            except Exception as e:
                self.logger.error("Error processing task %s: %s", task.task_id, e)
            finally:
                self.task_queue.task_done()

    def add_task(self, task: ThreadJob) -> None:
        """Add task to queue with specific parameters and job."""
        self.task_queue.put(task)

    def get_result(self, task_id: str) -> Optional[Any]:
        """Get the result of a specific task."""
        with self._lock:
            return self.results.get(task_id)

    def wait_completion(self):
        """Block until all tasks are done and stop all workers."""
        self.task_queue.join()

        # Signal all workers to exit
        for _ in range(self.num_workers):
            self.task_queue.put(None)

        # Wait for all worker threads to finish
        for worker in self.worker_threads:
            worker.join()


@dataclass
class AsyncTask:
    func: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.kwargs = self.kwargs or {}


class AsyncTaskManager:
    def __init__(self, maxsize: int = 5):
        self.maxsize = maxsize
        self.is_running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.task_queue: queue.Queue[AsyncTask] = queue.Queue()
        self.result_queue: queue.Queue[Any] = queue.Queue()
        self.current_tasks: List[asyncio.Task[Any]] = []
        self.sem = asyncio.Semaphore(self.maxsize)

    async def _consume_task(self) -> None:
        while True:
            self.current_tasks = [task for task in self.current_tasks if not task.done()]

            if self.task_queue.empty() and not self.current_tasks:
                break

            while not self.task_queue.empty() and len(self.current_tasks) < self.maxsize:
                try:
                    task = self.task_queue.get_nowait()
                    task_obj = asyncio.create_task(self.run_task(task))
                    self.current_tasks.append(task_obj)
                except queue.Empty:
                    break

            if self.current_tasks:
                await asyncio.wait(self.current_tasks, return_when=asyncio.FIRST_COMPLETED)

    async def run_task(self, task: AsyncTask) -> Any:
        async with self.sem:
            print(
                f"Task {task.func.__name__} with args {task.args} and kwargs {task.kwargs} start running!"
            )
            result = await task.func(*task.args, **task.kwargs)  # type: ignore
            self.result_queue.put(result)
            return result

    def produce_task(self, task: AsyncTask) -> None:
        self.task_queue.put(task)
        self._check_thread()

    def produce_task_list(self, tasks: List[AsyncTask]) -> None:
        for task in tasks:
            self.task_queue.put(task)
        self._check_thread()

    def get_result(self, max_item_retrieve: int = 3) -> list[Any]:
        items: list[Any] = []
        retrieve_all = max_item_retrieve == 0
        while retrieve_all or len(items) < max_item_retrieve:
            try:
                items.append(self.result_queue.get_nowait())
            except queue.Empty:
                break
        return items

    def _check_thread(self) -> None:
        with self._lock:
            if not self.is_running or self.thread is None or not self.thread.is_alive():
                self.is_running = True
                self.thread = threading.Thread(target=self._start_event_loop)
                self.thread.start()

    def _start_event_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._consume_task())
        finally:
            self.loop.close()
            self.loop = None
            self.is_running = False
            self.current_tasks.clear()

    def close_thread(self, timeout: Optional[int] = None) -> None:
        if self.thread is not None:
            self.thread.join(timeout=timeout)
            self.thread = None
