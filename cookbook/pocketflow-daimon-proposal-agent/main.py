import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from runner import run_agent_task
from utils import (
    DocumentExtractionError,
    MEMORY_PATH,
    load_env_file,
    load_or_build_memory,
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

    print(f"📝 Task: {args.task}")
    print(f"🗂️ Memory: {MEMORY_PATH}")
    result = run_agent_task(
        args.task,
        max_attempts=args.max_attempts,
        logs_dir=args.logs_dir,
        rebuild_memory=False,
    )
    artifacts = result["artifacts"]
    print(f"🧾 Logs: {artifacts['run_dir']}")

    print("\n=== Answer ===")
    print(result.get("answer", "(no answer generated)"))

    if result.get("reviewer_note"):
        print("\n=== Reviewer Note ===")
        print(result["reviewer_note"])

    print("\n=== Saved Artifacts ===")
    print(f"Trace JSON: {artifacts['trace_json']}")
    print(f"Trace Markdown: {artifacts['trace_md']}")
    print(f"Answer Markdown: {artifacts['answer_md']}")
    print(f"Answer PDF: {artifacts['answer_pdf']}")


if __name__ == "__main__":
    main()
