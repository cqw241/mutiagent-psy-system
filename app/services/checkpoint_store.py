"""Graph checkpoint backend factory.

当前环境未安装 langgraph 官方的 postgres/redis saver 扩展，因此本仓库内置：
- `memory`: 开发/测试默认
- `file`: 使用本地磁盘持久化，满足单机试点与进程重启恢复

`postgres` / `redis` 预留为未来生产化后端，若被选择则显式报错并提示缺少依赖，
避免静默退化到内存模式。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

from app.core.config import Settings
from langgraph.checkpoint.base import BaseCheckpointSaver, ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.memory import InMemorySaver, PersistentDict
from langchain_core.runnables import RunnableConfig


class FileCheckpointSaver(InMemorySaver):
    """基于磁盘文件的 LangGraph checkpointer。"""

    def __init__(self, directory: str) -> None:
        super().__init__()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

        self.storage = PersistentDict(
            lambda: defaultdict(dict),
            filename=str(self.directory / "storage.pkl"),
        )
        self.writes = PersistentDict(
            dict,
            filename=str(self.directory / "writes.pkl"),
        )
        self.blobs = PersistentDict(
            dict,
            filename=str(self.directory / "blobs.pkl"),
        )

        for store in (self.storage, self.writes, self.blobs):
            if Path(store.filename).exists():
                store.load()

    def _sync_all(self) -> None:
        self.storage.sync()
        self.writes.sync()
        self.blobs.sync()

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        with self._lock:
            next_config = super().put(config, checkpoint, metadata, new_versions)
            self._sync_all()
            return next_config

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        with self._lock:
            super().put_writes(config, writes, task_id, task_path)
            self._sync_all()

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            super().delete_thread(thread_id)
            self._sync_all()


def create_checkpointer(settings: Settings) -> BaseCheckpointSaver:
    """根据环境配置选择合适的 checkpointer。"""

    backend = settings.checkpoint_backend
    if backend == "memory":
        return InMemorySaver()
    if backend == "file":
        return FileCheckpointSaver(settings.checkpoint_dir)
    if backend == "postgres":
        raise RuntimeError(
            "CHECKPOINT_BACKEND=postgres requires the optional "
            "`langgraph-checkpoint-postgres` package, which is not installed."
        )
    if backend == "redis":
        raise RuntimeError(
            "CHECKPOINT_BACKEND=redis requires a Redis-backed LangGraph saver package, "
            "which is not installed."
        )
    raise ValueError(f"Unsupported checkpoint backend: {backend!r}")
