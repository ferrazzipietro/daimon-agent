import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flow import create_flow
from utils import (
    DocumentExtractionError,
    MEMORY_PATH,
    init_run_artifacts,
    load_env_file,
    load_or_build_memory,
    log_step,
    write_answer_files,
    write_trace_files,
)


def parse_args():
    parser = argparse.ArgumentParser(description="DAIMON Horizon proposal assistant")
    parser.add_argument(
        "task",
        nargs="?",
        default="What is missing in WP5?",
        help="Proposal question or writing task.",
    )
    parser.add_argument(
        "--rebuild-memory",
        action="store_true",
        help="Rebuild project_memory.json from data_daimon before answering.",
    )
    parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Print memory source inventory before the answer.",
    )
    parser.add_argument(
        "--inspect-memory",
        action="store_true",
        help="Print memory source inventory and exit without calling the LLM.",
    )
    parser.add_argument(
        "--logs-dir",
        default=None,
        help="Directory where per-run logs and answer PDFs are saved.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum generation/review attempts before accepting the latest answer.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    load_env_file(Path(__file__).resolve().parent / ".env")
    try:
        memory = load_or_build_memory(force_rebuild=args.rebuild_memory)
    except DocumentExtractionError as exc:
        print("Document extraction failed. The agent will not run with incomplete memory.")
        print(f"Reason: {exc}")
        print("Fix: install docling, or provide source files Docling can convert, then rebuild memory.")
        raise SystemExit(1) from exc

    if args.show_sources or args.inspect_memory:
        print("=== Memory Sources ===")
        for source in memory.get("sources", []):
            print(
                f"- {source['name']} | kind={source.get('kind')} | "
                f"priority={source.get('priority')} | chars={source.get('chars')}"
            )
        print()

    if args.inspect_memory:
        print("=== Current Updates ===")
        for update in memory.get("current_updates", []):
            print(f"- {update}")
        print(f"\nChunks indexed: {len(memory.get('chunks', []))}")
        return

    artifacts = init_run_artifacts(args.task, logs_dir=args.logs_dir)
    shared = {
        "task": args.task,
        "memory": memory,
        "skills_dir": str(Path(__file__).resolve().parent / "skills"),
        "attempt": 1,
        "max_attempts": max(1, args.max_attempts),
        "artifacts": artifacts,
        "trace": [],
    }
    log_step(
        shared,
        "RunStarted",
        {
            "task": args.task,
            "memory_path": str(MEMORY_PATH),
            "memory_sources": memory.get("sources", []),
            "max_attempts": shared["max_attempts"],
            "artifacts": artifacts,
        },
    )

    print(f"📝 Task: {args.task}")
    print(f"🗂️ Memory: {MEMORY_PATH}")
    print(f"🧾 Logs: {artifacts['run_dir']}")
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

    print("\n=== Answer ===")
    print(shared.get("result", shared.get("draft_answer", "(no answer generated)")))

    if shared.get("judge_feedback"):
        print("\n=== Reviewer Note ===")
        print(shared["judge_feedback"])

    print("\n=== Saved Artifacts ===")
    print(f"Trace JSON: {artifacts['trace_json']}")
    print(f"Trace Markdown: {artifacts['trace_md']}")
    print(f"Answer Markdown: {artifacts['answer_md']}")
    print(f"Answer PDF: {artifacts['answer_pdf']}")


if __name__ == "__main__":
    main()
