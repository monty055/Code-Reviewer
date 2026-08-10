"""Task creation and completion for the Task Tracker API."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class InvalidTaskError(ValueError):
    pass


@dataclass
class Task:
    id: str
    title: str
    due_date: datetime | None
    status: str = "pending"
    completed_at: datetime | None = None


_tasks: dict[str, Task] = {}


def create_task(title: str, due_date: datetime | None = None) -> Task:
    if not title or not title.strip():
        raise InvalidTaskError("A task title is required.")

    if due_date is not None and due_date <= datetime.now(timezone.utc):
        raise InvalidTaskError("Due date must be in the future.")

    task = Task(id=str(uuid.uuid4()), title=title.strip(), due_date=due_date, status="pending")
    _tasks[task.id] = task
    return task


def complete_task(task_id: str) -> Task:
    task = _tasks[task_id]
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    return task


def list_completed_tasks() -> list[Task]:
    return [t for t in _tasks.values() if t.status == "completed"]


def list_pending_tasks() -> list[Task]:
    return [t for t in _tasks.values() if t.status == "pending"]
