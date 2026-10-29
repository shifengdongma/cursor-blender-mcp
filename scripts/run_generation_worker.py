#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the background task worker(s) outside the Flask web process."""
from __future__ import absolute_import

import logging
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.config import Config
from backend.database import init_database
from backend.generation_worker import start_generation_worker
from backend.task_service import get_task_service
from backend.task_worker import start_task_worker


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    cfg = Config()
    init_database(cfg.DATA_DIR)
    task_service = get_task_service(cfg.DATA_DIR)

    stop_event = threading.Event()

    def _stop(signum, frame):
        logging.getLogger(__name__).info("Stopping worker (signal=%s)", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    # Legacy creative tasks (storyboard/tts/compose/refine/export).
    start_task_worker(task_service, cfg)
    # Resumable image/video generation tasks.
    threads = start_generation_worker(task_service, cfg, stop_event=stop_event)

    logging.getLogger(__name__).info(
        "Worker running (generation concurrency=%s)", cfg.GENERATION_WORKER_CONCURRENCY
    )
    while not stop_event.is_set():
        time.sleep(1)
    for thread, _ in threads:
        thread.join(timeout=5)
    logging.getLogger(__name__).info("Worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
