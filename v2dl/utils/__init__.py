# v2dl/utils/__init__.py
from .download import AlbumTracker, BaseDownloadAPI, ImageDownloadAPI, PathUtil
from .factory import DownloadAPIFactory, ServiceType, TaskServiceFactory
from .multitask import (
    AsyncService,
    BaseTaskService,
    Task,
    ThreadingService,
)
from .parser import LinkParser
from .security import AccountManager, Encryptor, KeyManager, SecureFileHandler

# only import __all__ when using from automation import *
__all__ = [
    "AccountManager",
    "AlbumTracker",
    "AsyncService",
    "BaseDownloadAPI",
    "BaseTaskService",
    "DownloadAPIFactory",
    "Encryptor",
    "ImageDownloadAPI",
    "KeyManager",
    "LinkParser",
    "PathUtil",
    "SecureFileHandler",
    "ServiceType",
    "Task",
    "TaskServiceFactory",
    "ThreadingService",
]
