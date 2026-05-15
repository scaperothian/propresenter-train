# propresenter-train — Claude context

## What this project does

CLI tool for recording a human trainer's slide-change timings against a fixed audio
file.  It plays back the audio, lets the trainer control ProPresenter slides
interactively, and writes a JSON file that mirrors the `/v1/presentation/{uuid}`
API response with two additions:

- `presentation.id.audio` — path of the audio file used for the session
- `"trigger time"` key on each triggered slide dict — seconds elapsed since audio start

The resulting JSON is the **gold copy** used to evaluate automated slide-cueing
systems (propresenter-speech, etc.) against the same audio file.

## Dependency layout

| Concern | Module |
|---------|--------|
| Training session + JSON build | `src/propresenter_train/trainer.py` — `TrainingSession` |
| CLI entry point | `src/propresenter_train/main.py` |
| ProPresenter HTTP client | `../propresenter-client/src/propresenter_client/main.py` — imported via path dep |

`TrainingSession` reuses `_get_command()` and `ProPresenterController` directly from
`propresenter-client` so the interactive prompt behaviour is identical to the standard
client's interactive mode.

## Key design decisions

- **Timing** — `time.perf_counter()` captures the trigger time *before* the
  ProPresenter API call (network latency excluded from the recorded time).
- **Traversal parity** — `_annotate()` in `trainer.py` mirrors
  `ProPresenterController.find_slides()` exactly so flat slide indices map
  identically in both the trigger-time dict and the output JSON.
- **Starting slide** — the active slide at audio-start is automatically recorded at
  `t = 0.0`.  If the trainer backtracks and re-triggers a slide, the newer time
  overwrites the older one.
- **Untriggered slides** — slides never reached by the trainer have no `"trigger time"`
  key in the output JSON.

## Project conventions

- **Python 3.11+** — native `list[...]` / `dict[...]` / `X | Y` type hints.
- **Poetry** for dependency management.  Run `poetry install` before anything.
- **No comments** unless the WHY is non-obvious.

## Running the project

```bash
# Install deps
poetry install

# Basic usage (positional args: audio file, presentation name)
poetry run propresenter-train audio/sermon.wav "Sunday Sermon"

# JSON lands in ./output/ by default; override with --output-dir
poetry run propresenter-train audio/pledge.wav "Pledge of Allegiance" --output-dir sessions/

# Skip activating the presentation (if already active in ProPresenter)
poetry run propresenter-train audio/service.wav "Service" --no-activate

# Remote ProPresenter host
poetry run propresenter-train audio/worship.wav "Worship" --host 192.168.1.10

# Search a non-default library
poetry run propresenter-train audio/song.wav "Amazing Grace" --library Songs
```

## Running tests

```bash
poetry run pytest              # all tests
poetry run pytest -v           # verbose
```

Tests are unit-level — no audio hardware, no ProPresenter server required.
`sounddevice` and `soundfile` are not called in tests; all I/O is mocked.

## Interactive commands during training

| Key | Action |
|-----|--------|
| `n` | Next slide (fires on keypress, no Enter) |
| `b` | Previous slide (fires on keypress, no Enter) |
| `<number>` + Enter | Jump to slide N (1-indexed) |
| `q` | Save JSON and quit |
| Ctrl+C | Interrupt — saves partial results then exits |

## Output JSON shape

```json
{
  "presentation": {
    "id": {
      "uuid": "...",
      "name": "My Presentation",
      "index": 0,
      "audio": "audio/sermon.wav"
    },
    "groups": [
      {
        "name": "",
        "color": null,
        "slides": [
          {
            "enabled": true,
            "notes": "",
            "trigger time": 0.0,
            "text": "Opening words",
            "label": ""
          },
          {
            "enabled": true,
            "notes": "",
            "trigger time": 12.43,
            "text": "Second slide",
            "label": ""
          }
        ]
      }
    ]
  }
}
```

The file is written to `<output-dir>/<presentation-name>.json`.
Characters illegal on any OS (`\ / : * ? " < > |`) are replaced with `_`.
