import logging
import threading
from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable, Generic, Optional, TypeVar, Union

# Generic type for task input and task result
TI = TypeVar("TI", bound=Any)
TR = TypeVar("TR", bound=Any)


@dataclass
class ThreadJob(Generic[TI]):
    """Generic task container."""

    task_id: str
    params: TI
    job: Union[Callable[..., TR], Any] = None  # type: ignore


class ThreadingService(Generic[TI, TR]):
    """Generic service for processing tasks with multiple workers."""

    def __init__(self, logger: logging.Logger, num_workers: int = 1):
        self.task_queue: Queue[Optional[ThreadJob[TI]]] = Queue()
        self.logger = logger
        self.num_workers = num_workers
        self.worker_threads: list[threading.Thread] = []
        self.results: dict[str, TR] = {}
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
                if task.job:
                    result: Any = task.job(task.task_id, task.params, self.logger)
                    with self._lock:
                        self.results[task.task_id] = result
            except Exception as e:
                self.logger.error("Error processing task %s: %s", task.task_id, e)
            finally:
                self.task_queue.task_done()

    def add_task(self, task_id: str, params: TI, job: Any) -> None:
        """Add task to queue with specific parameters and job."""
        task = ThreadJob(task_id=task_id, params=params, job=job)
        self.task_queue.put(task)

    def get_result(self, task_id: str) -> Optional[TR]:
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
