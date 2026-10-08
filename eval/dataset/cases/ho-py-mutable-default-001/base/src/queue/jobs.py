def enqueue(job: str, queue: list[str] | None = None) -> list[str]:
    queue = [] if queue is None else queue
    queue.append(job)
    return queue
