# -*- coding: utf-8 -*-
"""Resumable worker for image/video generation tasks."""
from __future__ import absolute_import

import logging
import os
import socket
import threading
import time
import uuid

from . import generation_service
from .http_utils import ApiError

logger = logging.getLogger(__name__)


class GenerationWorker(object):
    def __init__(self, task_service, cfg, name=None):
        self.task_service = task_service
        self.cfg = cfg
        self.name = name or "generation-worker"
        self._counter = 0
        self._last_action = None

    def _lease_owner(self):
        self._counter += 1
        return "{0}:{1}:{2}:{3}".format(
            self.name, socket.gethostname(), os.getpid(), uuid.uuid4().hex[:12]
        )

    def recover(self):
        try:
            self.task_service.recover_stale_generation_leases()
        except Exception:
            logger.exception("Failed to recover stale generation leases")

    def _poll_once(self):
        task = self.task_service.claim_generation_poll(
            self._lease_owner(), lease_seconds=self.cfg.GENERATION_TASK_LEASE_SECONDS
        )
        if task is None:
            return False
        lease_owner = task.lease_owner
        try:
            generation_service.poll_task(self.cfg, self.task_service, task, lease_owner)
        except ApiError as exc:
            self.task_service.release_generation_lease(
                task.id, lease_owner, status="failed", stage="failed",
                error_code=exc.code, error_message=exc.message,
                completed_at=int(time.time()), completed_at_ms=time.time(),
            )
        except Exception as exc:
            logger.exception("Generation poll failed for %s", task.id)
            generation_service._handle_poll_error(
                self.cfg, self.task_service, task, lease_owner, exc
            )
        return True

    def _submit_once(self):
        task = self.task_service.claim_generation_submission(
            self._lease_owner(), lease_seconds=self.cfg.GENERATION_TASK_LEASE_SECONDS
        )
        if task is None:
            return False
        lease_owner = task.lease_owner
        try:
            generation_service.submit_task(self.cfg, self.task_service, task, lease_owner)
        except ApiError as exc:
            self.task_service.release_generation_lease(
                task.id, lease_owner, status="failed", stage="failed",
                error_code=exc.code, error_message=exc.message,
                completed_at=int(time.time()), completed_at_ms=time.time(),
            )
        except Exception:
            logger.exception("Generation submission failed for %s", task.id)
            self.task_service.release_generation_lease(
                task.id, lease_owner, status="needs_review", stage="needs_review",
                error_code="submission_uncertain",
                error_message="提交阶段异常，需人工确认是否已创建第三方任务",
                submission_uncertain=1,
                completed_at=int(time.time()), completed_at_ms=time.time(),
            )
        return True

    def run_once(self):
        # Alternate submission and polling so a backlog of due polls cannot
        # indefinitely starve new paid jobs.  The lease/claim SQL is unchanged.
        order = ("submit", "poll") if self._last_action == "poll" else ("poll", "submit")
        for action in order:
            worked = self._submit_once() if action == "submit" else self._poll_once()
            if worked:
                self._last_action = action
                return True
        return False

    def run_forever(self, stop_event):
        self.recover()
        last_recovery = time.monotonic()
        interval = max(10, int(getattr(self.cfg, "GENERATION_RECOVERY_INTERVAL_S", 60)))
        logger.info("%s started", self.name)
        while not stop_event.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("%s loop error", self.name)
                worked = False
            if time.monotonic() - last_recovery >= interval:
                self.recover()
                last_recovery = time.monotonic()
            if not worked:
                stop_event.wait(self.cfg.GENERATION_WORKER_POLL_INTERVAL_S)
        logger.info("%s stopped", self.name)


def start_generation_worker(task_service, cfg, concurrency=None, stop_event=None):
    stop_event = stop_event or threading.Event()
    count = concurrency or cfg.GENERATION_WORKER_CONCURRENCY
    threads = []
    for index in range(max(1, int(count))):
        worker = GenerationWorker(task_service, cfg, name="generation-worker-{0}".format(index))
        thread = threading.Thread(target=worker.run_forever, args=(stop_event,))
        thread.daemon = True
        thread.start()
        threads.append((thread, stop_event))
    return threads
