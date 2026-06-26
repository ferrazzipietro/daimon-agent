import argparse
import os
import sys


def ensure_repo_on_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(base_dir, "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


ensure_repo_on_path()

from flow import create_export_intelligence_flow
from utils import DEFAULT_SEEDS


def parse_args():
    parser = argparse.ArgumentParser(description="AI Export Intelligence")
    parser.add_argument("--countries", type=str, default=None)
    parser.add_argument("--sectors", type=str, default=None)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--threshold", type=int, default=60)
    parser.add_argument("--seeds-file", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    seeds = DEFAULT_SEEDS.copy()

    if args.countries:
        seeds["countries"] = [c.strip() for c in args.countries.split(",") if c.strip()]
    if args.sectors:
        seeds["sectors"] = [s.strip() for s in args.sectors.split(",") if s.strip()]

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or os.path.join(base_dir, "outputs")

    shared = {
        "seeds": seeds,
        "seeds_file": args.seeds_file,
        "max_results": args.max_results,
        "top_n": args.top,
        "score_threshold": args.threshold,
        "output_dir": output_dir,
    }

    flow = create_export_intelligence_flow()
    print("Starting AI Export Intelligence")
    print("=" * 60)
    flow.run(shared)


if __name__ == "__main__":
    main()
