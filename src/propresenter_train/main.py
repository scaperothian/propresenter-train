"""
CLI entry point for propresenter-train.

Usage examples:
  propresenter-train audio/sermon.wav "Sunday Sermon"
  propresenter-train audio/pledge.wav "Pledge of Allegiance" --output-dir sessions/
  propresenter-train audio/worship.wav "Worship Set" --host 192.168.1.10 --no-activate
  propresenter-train audio/service.wav "Service" --library Songs
"""

import argparse
import logging
import sys
from pathlib import Path

from propresenter_client.main import ProPresenterController

from .trainer import TrainingSession


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="propresenter-train",
        description=(
            "Play an audio file and record human slide-trigger timings for a "
            "ProPresenter presentation.  Saves a gold-copy JSON that matches "
            "the /v1/presentation/{uuid} response shape with an extra "
            "'trigger time' key on each triggered slide."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "audio",
        metavar="AUDIO_FILE",
        help="Audio file to play during the training session (WAV, FLAC, OGG, …)",
    )
    parser.add_argument(
        "presentation",
        metavar="PRESENTATION_NAME",
        help="ProPresenter presentation name (case-insensitive substring match)",
    )

    conn = parser.add_argument_group("ProPresenter connection")
    conn.add_argument("--host", default="localhost", help="ProPresenter hostname or IP")
    conn.add_argument("--port", type=int, default=1025, help="ProPresenter API port")
    conn.add_argument("--timeout", type=int, default=5, help="HTTP timeout (seconds)")

    pres_grp = parser.add_argument_group("Presentation")
    pres_grp.add_argument(
        "--library",
        default="Default",
        metavar="NAME",
        help="Library to search for the named presentation",
    )
    pres_grp.add_argument(
        "--no-activate",
        action="store_true",
        dest="no_activate",
        help="Skip activating the presentation (use when it is already active)",
    )

    out_grp = parser.add_argument_group("Output")
    out_grp.add_argument(
        "--output-dir",
        default=".",
        metavar="DIR",
        dest="output_dir",
        help="Directory in which to write the JSON timing file",
    )

    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        dest="log_level",
        help="Logging verbosity",
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

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(f"Error: Audio file not found: {audio_path}")
        sys.exit(1)

    pro = ProPresenterController(host=args.host, port=args.port, timeout=args.timeout)
    if pro.get_status() is None:
        print(
            f"Error: Cannot reach ProPresenter at {args.host}:{args.port}.\n"
            "Make sure ProPresenter is running and the Network API is enabled."
        )
        sys.exit(1)
    print(f"Connected to ProPresenter at {args.host}:{args.port}")

    library_data = pro.get_library(args.library)
    if library_data is None:
        print(f"Error: Could not query '{args.library}' library.")
        sys.exit(1)

    uuid = pro.find_presentation_uuid_by_name(args.presentation, library_data)
    if uuid is None:
        print(f"Error: Presentation '{args.presentation}' not found in '{args.library}' library.")
        sys.exit(1)

    if not args.no_activate:
        if not pro.activate_presentation(uuid):
            print(f"Error: Failed to activate '{args.presentation}'.")
            sys.exit(1)
        print(f"Activated '{args.presentation}' (UUID: {uuid})")
    else:
        print(f"Using '{args.presentation}' (UUID: {uuid})")

    details = pro.get_presentation_details(uuid)
    if details is None:
        print(f"Error: Could not fetch presentation details for UUID {uuid}.")
        sys.exit(1)

    session = TrainingSession(
        controller=pro,
        presentation_details=details,
        audio_path=audio_path,
    )

    try:
        session.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted — saving partial results...")

    session.save(Path(args.output_dir))


if __name__ == "__main__":
    main()
