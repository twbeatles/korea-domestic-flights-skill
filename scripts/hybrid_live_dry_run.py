#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common_cli import close_safely, emit_json, normalize_airport, parse_flexible_date, resolve_source_repo, source_repo_candidates



def main():
    parser = argparse.ArgumentParser(description="Shallow live dry-run / DOM drift sanity check for korea-domestic-flights")
    parser.add_argument("--origin", default="김포")
    parser.add_argument("--destination", default="제주")
    parser.add_argument("--departure", default="내일", help="1-day live probe 에 사용할 날짜")
    parser.add_argument("--probe", action="store_true", help="실제로 1일 broad scan 을 시도합니다. 없으면 환경/임포트만 확인합니다.")
    parser.add_argument("--repo-path", help="upstream Scraping-flight-information 저장소 경로")
    args = parser.parse_args()

    searched_candidates = source_repo_candidates(script_path=__file__, repo_path=args.repo_path)
    try:
        repo_path = resolve_source_repo(script_path=__file__, repo_path=args.repo_path)
    except FileNotFoundError:
        repo_path = searched_candidates[0]
    report = {
        "status": "ok",
        "mode": "live_probe" if args.probe else "env_only",
        "checks": [],
        "repo_path": str(repo_path),
        "searched_candidates": [str(path) for path in searched_candidates],
        "probe": None,
    }

    report["checks"].append({"name": "repo_exists", "ok": repo_path.exists()})
    if not repo_path.exists():
        report["status"] = "degraded"
        emit_json(report)
        sys.exit(0)

    sys.path.insert(0, str(repo_path))

    try:
        from scraping.parallel import ParallelSearcher
    except Exception as exc:
        report["status"] = "degraded"
        report["checks"].append({"name": "import_parallel_searcher", "ok": False, "error": str(exc)})
        emit_json(report)
        sys.exit(0)

    report["checks"].append({"name": "import_parallel_searcher", "ok": True})

    if not args.probe:
        emit_json(report)
        return

    try:
        origin = normalize_airport(args.origin)
        destination = normalize_airport(args.destination)
        departure = parse_flexible_date(args.departure).strftime("%Y%m%d")
    except Exception as exc:
        report["status"] = "degraded"
        report["probe"] = {"ok": False, "error": f"invalid route input: {exc}"}
        emit_json(report)
        sys.exit(0)

    searcher = ParallelSearcher()
    probe_logs = []
    try:
        raw = searcher.search_date_range(
            origin=origin,
            destination=destination,
            dates=[departure],
            return_offset=0,
            adults=1,
            cabin_class="ECONOMY",
            progress_callback=lambda msg: probe_logs.append(str(msg)),
        )
        report["probe"] = {
            "ok": isinstance(raw, dict),
            "route": f"{origin}-{destination}",
            "departure": departure,
            "raw_type": type(raw).__name__,
            "keys": list(raw.keys())[:5],
            "log_preview": probe_logs[:10],
            "note": "1-day broad scan probe completed. This validates import + shallow execution path without asserting fare availability.",
        }
    except TypeError as exc:
        report["status"] = "degraded"
        report["probe"] = {
            "ok": False,
            "route": f"{origin}-{destination}",
            "error": str(exc),
            "note": "ParallelSearcher.search_date_range signature or call contract may have drifted.",
        }
    except Exception as exc:
        report["status"] = "degraded"
        report["probe"] = {
            "ok": False,
            "route": f"{origin}-{destination}",
            "error": str(exc),
            "log_preview": probe_logs[:10],
            "note": "Live probe failed; inspect upstream scraper/browser environment or DOM drift.",
        }
    finally:
        close_safely(searcher)

    emit_json(report)


if __name__ == "__main__":
    main()
