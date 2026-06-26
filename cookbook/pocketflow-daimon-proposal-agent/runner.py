from __future__ import annotations

from pathlib import Path

from flow import create_flow
from utils import (
    MEMORY_PATH,
    init_run_artifacts,
    load_or_build_memory,
    log_step,
    write_answer_files,
    write_trace_files,
)


AGENT_DIR = Path(__file__).resolve().parent


def run_agent_task(
    task: str,
    max_attempts: int = 2,
    logs_dir: str | None = None,
    rebuild_memory: bool = False,
) -> dict:
    memory = load_or_build_memory(force_rebuild=rebuild_memory)
    artifacts = init_run_artifacts(task, logs_dir=logs_dir)
    shared = {
        "task": task,
        "memory": memory,
        "skills_dir": str(AGENT_DIR / "skills"),
        "attempt": 1,
        "max_attempts": max(1, max_attempts),
        "artifacts": artifacts,
        "trace": [],
    }
    log_step(
        shared,
        "RunStarted",
        {
            "task": task,
            "memory_path": str(MEMORY_PATH),
            "memory_sources": memory.get("sources", []),
            "max_attempts": shared["max_attempts"],
            "artifacts": artifacts,
        },
    )

    create_flow().run(shared)

    log_step(
        shared,
        "RunCompleted",
        {
            "review_status": shared.get("review_status"),
            "final_attempt": shared.get("attempt"),
            "answer_chars": len(shared.get("result", shared.get("draft_answer", ""))),
        },
    )
    write_answer_files(shared)
    write_trace_files(shared)

    return {
        "answer": shared.get("result", shared.get("draft_answer", "")),
        "reviewer_note": shared.get("judge_feedback", ""),
        "review_status": shared.get("review_status"),
        "intent": shared.get("intent"),
        "selected_skill": shared.get("selected_skill"),
        "artifacts": artifacts,
        "trace": shared.get("trace", []),
    }
