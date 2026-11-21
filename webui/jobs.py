from __future__ import annotations

"""File d'attente des recherches et suivi de progression."""

import secrets
import threading
import time
import traceback
from dataclasses import dataclass, field

from imagefinder.service import run_download


class JobConflict(RuntimeError):
    """Une recherche est deja en cours."""


@dataclass
class Job:
    id: str
    request: str
    folder: str
    output_dir: str
    limit: int
    source: str
    orientation: str
    min_side: int
    inbox_mode: bool = False
    inbox_folder: str = "inbox"
    status: str = "queued"
    stage: str = "queued"
    message: str = "En attente..."
    progress: int = 0
    done: int = 0
    total: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    log: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    cancelled: bool = False

    def payload(self) -> dict:
        end = self.finished_at or time.time()
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "progress": self.progress,
            "done": self.done,
            "total": self.total,
            "request": self.request,
            "folder": self.folder,
            "limit": self.limit,
            "source": self.source,
            "orientation": self.orientation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "elapsed": round(max(0.0, end - self.created_at), 1),
            "log": self.log[-30:],
            "result": self.result,
            "error": self.error,
            "cancelled": self.cancelled,
        }


class JobManager:
    def __init__(self, max_jobs: int = 40) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._active_id: str | None = None
        self._max_jobs = max_jobs

    def _active_locked(self) -> Job | None:
        if not self._active_id:
            return None
        job = self._jobs.get(self._active_id)
        if job is None or job.status not in {"queued", "running"}:
            self._active_id = None
            return None
        return job

    def active(self) -> dict | None:
        with self._lock:
            job = self._active_locked()
            return job.payload() if job else None

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.payload()

    def submit(
        self,
        *,
        request: str,
        folder: str,
        output_dir: str,
        limit: int,
        source: str,
        orientation: str,
        min_side: int,
        inbox_mode: bool = False,
        inbox_folder: str = "inbox",
    ) -> dict:
        with self._lock:
            active = self._active_locked()
            if active is not None:
                raise JobConflict(
                    "une recherche est deja en cours, attendez la fin avant d'en lancer une autre"
                )

            job = Job(
                id=secrets.token_hex(8),
                request=request,
                folder=folder,
                output_dir=output_dir,
                limit=limit,
                source=source,
                orientation=orientation,
                min_side=min_side,
                inbox_mode=inbox_mode,
                inbox_folder=inbox_folder,
            )
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._active_id = job.id
            while len(self._order) > self._max_jobs:
                old = self._order.pop(0)
                if old != self._active_id:
                    self._jobs.pop(old, None)

            thread = threading.Thread(
                target=self._run,
                args=(job.id,),
                name=f"image-finder-job-{job.id[:6]}",
                daemon=True,
            )
            thread.start()
            return job.payload()

    def cancel(self, job_id: str) -> None:
        """Annule la recherche en cours (marque le job comme annule)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status not in {"queued", "running"}:
                return
            job.cancelled = True
            job.status = "cancelled"
            job.stage = "cancelled"
            job.message = "Recherche annulee par l'utilisateur"
            job.finished_at = time.time()
            job.updated_at = job.finished_at
            if self._active_id == job_id:
                self._active_id = None

    def _run(self, job_id: str) -> None:
        def report(event: dict) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "running"
                job.stage = str(event.get("stage") or job.stage)
                message = event.get("message")
                if message:
                    job.message = str(message)
                if "progress" in event:
                    try:
                        job.progress = max(0, min(100, int(event["progress"])))
                    except (TypeError, ValueError):
                        pass
                if "done" in event:
                    try:
                        job.done = max(0, int(event["done"]))
                    except (TypeError, ValueError):
                        pass
                if "total" in event:
                    try:
                        job.total = max(0, int(event["total"]))
                    except (TypeError, ValueError):
                        pass
                job.updated_at = time.time()
                if message and (not job.log or job.log[-1] != str(message)):
                    job.log.append(str(message))
                    job.log = job.log[-40:]

        try:
            result = run_download(
                job_request := self._job_field(job_id, "request"),
                output=self._job_field(job_id, "output_dir"),
                limit=self._job_field(job_id, "limit"),
                source=self._job_field(job_id, "source"),
                orientation=self._job_field(job_id, "orientation"),
                min_side=self._job_field(job_id, "min_side"),
                workers=6,
                gallery=True,
                progress=report,
                inbox_mode=self._job_field(job_id, "inbox_mode"),
                inbox_folder=self._job_field(job_id, "inbox_folder"),
            )
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "done"
                job.stage = "done"
                job.progress = 100
                count = int(result.get("count") or 0)
                job.message = f"{count} image(s) enregistree(s)"
                job.finished_at = time.time()
                job.updated_at = job.finished_at
                job.done = count
                job.total = max(job.total, count)
                job.result = {
                    "query": result.get("query", job_request),
                    "folder": self._job_field(job_id, "folder"),
                    "output_dir": result.get("output_dir", ""),
                    "count": count,
                    "requested": result.get("requested", job.limit),
                    "downloaded": result.get("downloaded", 0),
                    "rejected": result.get("rejected", 0),
                    "files": list(result.get("files") or [])[:60],
                }
                for line in result.get("log") or []:
                    text = str(line).strip()
                    if text and (not job.log or job.log[-1] != text):
                        job.log.append(text)
                job.log = job.log[-60:]
        except Exception as exc:
            traceback.print_exc()
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "error"
                job.stage = "error"
                job.error = str(exc)
                job.message = str(exc)
                job.finished_at = time.time()
                job.updated_at = job.finished_at
                job.log.append(str(exc))
        finally:
            with self._lock:
                if self._active_id == job_id:
                    self._active_id = None

    def _job_field(self, job_id: str, field_name: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise RuntimeError("tache introuvable")
            return getattr(job, field_name)
