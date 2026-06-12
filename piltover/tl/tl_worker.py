import os
from concurrent.futures.thread import ThreadPoolExecutor

TL_WORKER = ThreadPoolExecutor(
    max_workers=min(1, (os.cpu_count() or 0) // 2),
    thread_name_prefix="TLWorker",
)
