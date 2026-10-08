def enqueue(job: str, queue: list[str] = []) -> list[str]:
    queue.append(job)
    return queue
