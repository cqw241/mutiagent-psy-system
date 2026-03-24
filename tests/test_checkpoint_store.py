from pathlib import Path

from app.core.config import Settings
from app.services.checkpoint_store import FileCheckpointSaver, create_checkpointer


def test_create_checkpointer_returns_in_memory_saver_by_default():
    saver = create_checkpointer(Settings())
    assert saver.__class__.__name__ in {"InMemorySaver", "MemorySaver"}


def test_file_checkpointer_persists_latest_checkpoint_between_instances(tmp_path):
    checkpoint_dir = tmp_path / "graph-checkpoints"
    saver = create_checkpointer(
        Settings(
            checkpoint_backend="file",
            checkpoint_dir=str(checkpoint_dir),
        )
    )

    config = {
        "configurable": {
            "thread_id": "thread-persist",
            "checkpoint_ns": "",
        }
    }
    checkpoint = {
        "v": 2,
        "id": "checkpoint-1",
        "ts": "2026-03-23T00:00:00+00:00",
        "channel_values": {"chat_history": [{"role": "user", "content": "hello"}]},
        "channel_versions": {"chat_history": "0001.0001"},
        "versions_seen": {},
        "pending_sends": [],
        "updated_channels": ["chat_history"],
    }
    metadata = {"source": "input", "step": -1}

    saver.put(config, checkpoint, metadata, {"chat_history": "0001.0001"})
    assert isinstance(saver, FileCheckpointSaver)

    reopened = create_checkpointer(
        Settings(
            checkpoint_backend="file",
            checkpoint_dir=str(checkpoint_dir),
        )
    )

    restored = reopened.get_tuple({"configurable": {"thread_id": "thread-persist"}})
    assert restored is not None
    assert restored.checkpoint["channel_values"]["chat_history"][0]["content"] == "hello"
