from redis import Redis
from rq import Worker

from .config import QUEUE_NAME, REDIS_URL
from .storage import ensure_storage_dirs


def main() -> None:
    ensure_storage_dirs()
    redis_conn = Redis.from_url(REDIS_URL)
    worker = Worker([QUEUE_NAME], connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()

