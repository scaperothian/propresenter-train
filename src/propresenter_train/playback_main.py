"""
CLI entry point for propresenter-train-playback.

Usage examples:
  propresenter-train-playback output/sermon.json
  propresenter-train-playback output/sermon.json --no-activate
  propresenter-train-playback output/sermon.json --host 192.168.1.10
  propresenter-train-playback output/sermon.json --device 1
"""

import argparse
import logging
import sys
from pathlib import Path

from propresenter_client.main import ProPresenterController

from .playback import PlaybackSession


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="propresenter-train-playback",
        description=(
            "Play back a propresenter-train gold-copy JSON: fires slide triggers "
            "at the recorded timestamps while playing the training audio so you "
            "can evaluate how well the timings work."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "json_file",
        metavar="JSON_FILE",
        help="Gold-copy JSON file produced by propresenter-train",
    )

    conn = parser.add_argument_group("ProPresenter connection")
    conn.add_argument("--host", default="localhost", help="ProPresenter hostname or IP")
    conn.add_argument("--port", type=int, default=1025, help="ProPresenter API port")
    conn.add_argument("--timeout", type=int, default=5, help="HTTP timeout (seconds)")

    parser.add_argument(
        "--library",
        default="Default",
        metavar="NAME",
        help="Library to search for the presentation (used to resolve a fresh UUID)",
    )
    parser.add_argument(
        "--no-activate",
        action="store_true",
        dest="no_activate",
        help="Skip activating the presentation before playback",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        metavar="INDEX",
        help="Output audio device index (run 'python -m sounddevice' to list; default: system default)",
    )
    parser.add_argument(
        "--early-trigger-window",
        type=float,
        default=0.2,
        metavar="SECONDS",
        dest="early_trigger_window",
        help="Fire each slide trigger this many seconds before the recorded cue time (default: 0.2)",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        dest="log_level",
    )

    return parser


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    json_path = Path(args.json_file)
    if not json_path.is_file():
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)

    pro = ProPresenterController(host=args.host, port=args.port, timeout=args.timeout)
    if pro.get_status() is None:
        print(
            f"Error: Cannot reach ProPresenter at {args.host}:{args.port}.\n"
            "Make sure ProPresenter is running and the Network API is enabled."
        )
        sys.exit(1)
    print(f"Connected to ProPresenter at {args.host}:{args.port}")

    try:
        session = PlaybackSession(controller=pro, json_path=json_path, device=args.device)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not args.no_activate:
        name = session.presentation_name
        library_data = pro.get_library(args.library)
        uuid = pro.find_presentation_uuid_by_name(name, library_data) if library_data else None
        if uuid and pro.activate_presentation(uuid):
            print(f"Activated '{name}' (UUID: {uuid})")
        else:
            print(f"Warning: Could not activate '{name}' — ensure it is already active in ProPresenter.")

    try:
        session.run(early_trigger_window=args.early_trigger_window)
        print("\nPlayback complete.")
    except KeyboardInterrupt:
        print("\n\nStopped.")


if __name__ == "__main__":
    main()
