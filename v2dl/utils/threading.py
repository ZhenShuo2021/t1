import queue
import asyncio
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from logging import Logger
from queue import Queue
from typing import Any


@dataclass
class Task:
    """Unified task container for both threading and async services."""

    task_id: str
    func: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.kwargs = self.kwargs or {}


class ServiceType(Enum):
    """Service type enumeration."""

    THREADING = "threading"
    ASYNC = "async"


class TaskService(ABC):
    """Abstract base class for task processing services."""

    @abstractmethod
    def start(self) -> None:
        """Start the service."""
        pass

    @abstractmethod
    def add_task(self, task: Task) -> None:
        """Add single task to queue."""
        pass

    @abstractmethod
    def add_tasks(self, tasks: list[Task]) -> None:
        """Add multiple tasks to queue."""
        pass

    @abstractmethod
    def get_result(self, task_id: str) -> Any | None:
        """Get result for specific task ID."""
        pass

    @abstractmethod
    def get_results(self, max_results: int = 0) -> dict[str, Any]:
        """Get all available results."""
        pass

    @abstractmethod
    def stop(self, timeout: int | None = None) -> None:
        """Stop the service."""
        pass


class ThreadingService(TaskService):
    """Service for processing tasks with multiple workers."""

    def __init__(self, logger: Logger, max_workers: int = 5):
        self.task_queue: Queue[Task | None] = Queue()
        self.logger = logger
        self.max_workers = max_workers
        self.workers: list[threading.Thread] = []
        self.results: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.is_running = False

    def start(self) -> None:
        if not self.is_running:
            self.is_running = True
            for _ in range(self.max_workers):
                worker = threading.Thread(target=self._process_tasks, daemon=True)
                self.workers.append(worker)
                worker.start()

    def _process_tasks(self) -> None:
        while True:
            task = self.task_queue.get()
            if task is None:
                break

            try:
                result = task.func(*task.args, **task.kwargs)  # type: ignore
                with self._lock:
                    self.results[task.task_id] = result
            except Exception as e:
                self.logger.error("Error processing task %s: %s", task.task_id, e)
            finally:
                self.task_queue.task_done()

    def add_task(self, task: Task) -> None:
        self.task_queue.put(task)
        if not self.is_running:
            self.start()

    def add_tasks(self, tasks: list[Task]) -> None:
        for task in tasks:
            self.task_queue.put(task)
        if not self.is_running:
            self.start()

    def get_result(self, task_id: str) -> Any | None:
        with self._lock:
            return self.results.get(task_id)

    def get_results(self, max_results: int = 0) -> dict[str, Any]:
        with self._lock:
            return self.results.copy()

    def stop(self, timeout: int | None = None) -> None:
        self.task_queue.join()
        for _ in range(self.max_workers):
            self.task_queue.put(None)
        for worker in self.workers:
            worker.join(timeout=timeout)
        self.workers.clear()
        self.is_running = False


class AsyncService(TaskService):
    def __init__(self, logger: Logger, maxsize: int = 5) -> None:
        self.maxsize = maxsize
        self.logger = logger
        self.is_running = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self.task_queue: queue.Queue[Task] = queue.Queue()
        self.result_queue: queue.Queue[Any] = queue.Queue()
        self.current_tasks: list[asyncio.Task[Any]] = []
        self.sem = asyncio.Semaphore(self.maxsize)

    def start(self) -> None:
        pass  # does not need

    def add_task(self, task: Task) -> None:
        self.task_queue.put(task)
        self._check_thread()

    def add_tasks(self, tasks: list[Task]) -> None:
        for task in tasks:
            self.task_queue.put(task)
        self._check_thread()

    def get_result(self, task_id: str) -> Any | None:
        raise NotImplementedError

    def get_results(self, max_item_retrieve: int = 3) -> list[Any]:
        items: list[Any] = []
        retrieve_all = max_item_retrieve == 0
        while retrieve_all or len(items) < max_item_retrieve:
            try:
                items.append(self.result_queue.get_nowait())
            except queue.Empty:
                break
        return items

    async def _process_tasks(self) -> None:
        while True:
            self.current_tasks = [task for task in self.current_tasks if not task.done()]

            if self.task_queue.empty() and not self.current_tasks:
                break

            while not self.task_queue.empty() and len(self.current_tasks) < self.maxsize:
                try:
                    task = self.task_queue.get_nowait()
                    task_obj = asyncio.create_task(self._run_task(task))
                    self.current_tasks.append(task_obj)
                except queue.Empty:
                    break

            if self.current_tasks:
                await asyncio.wait(self.current_tasks, return_when=asyncio.FIRST_COMPLETED)

    async def _run_task(self, task: Task) -> Any:
        async with self.sem:
            result = await task.func(*task.args, **task.kwargs)  # type: ignore
            self.result_queue.put(result)
            return result

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
            self.loop.run_until_complete(self._process_tasks())
        finally:
            self.loop.close()
            self.loop = None
            self.is_running = False
            self.current_tasks.clear()

    def stop(self, timeout: int | None = None) -> None:
        if self.thread is not None:
            self.thread.join(timeout=timeout)
            self.thread = None
            self.is_running = False


class TaskServiceFactory:
    """Factory class for creating task services."""

    @staticmethod
    def create(
        service_type: ServiceType,
        logger: Logger,
        max_workers: int = 5,
    ) -> TaskService:
        """Create a new task service instance."""
        if service_type == ServiceType.THREADING:
            return ThreadingService(logger, max_workers)
        elif service_type == ServiceType.ASYNC:
            return AsyncService(logger, max_workers)
        else:
            raise ValueError(f"Unknown service type: {service_type}")
