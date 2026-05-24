# propresenter-train — Claude context

## What this project does

CLI tool for recording a human trainer's slide timings against a fixed audio file.
It plays back the audio, lets the trainer control ProPresenter slides interactively,
and writes a JSON file that mirrors the `/v1/presentation/{uuid}` API response with
per-slide timing keys added. Supports two modes:

| Mode | CLI flag | JSON keys added to each slide |
|------|----------|-------------------------------|
| `trigger-label` (default) | `--mode trigger-label` | `"trigger time"` — when the slide was cued |
| `slide-label` | `--mode slide-label` | `"start time"` and `"stop time"` — audio section boundaries |

In both modes `presentation.id.audio` is added with the path of the training audio file.

All timing values are **lists of floats** (seconds since audio start) to support
multiple triggers per slide within a single session.

The resulting JSON is the **gold copy** used to evaluate automated slide-cueing
systems (propresenter-speech, etc.) against the same audio file.

## Dependency layout

| Concern | Module |
|---------|--------|
| Training session + JSON build | `src/propresenter_train/trainer.py` — `TrainingSession` |
| CLI entry point | `src/propresenter_train/main.py` |
| Playback engine | `src/propresenter_train/playback.py` — `PlaybackSession`, `load_cues()` |
| Playback CLI entry point | `src/propresenter_train/playback_main.py` |
| Mode constants | `trainer.py` — `MODE_TRIGGER_LABEL`, `MODE_SLIDE_LABEL` |
| ProPresenter HTTP client | `../propresenter-client/src/propresenter_client/main.py` — imported via path dep |

`TrainingSession` reuses `_get_command()` and `ProPresenterController` directly from
`propresenter-client` so the interactive prompt behaviour is identical to the standard
client's interactive mode.

## Key design decisions

- **Timing** — `time.perf_counter()` captures the trigger time *before* the
  ProPresenter API call so network latency is excluded from the recorded value.
- **Traversal parity** — `_annotate()` in `trainer.py` mirrors
  `ProPresenterController.find_slides()` exactly so flat slide indices map
  identically in both the in-memory timing dicts and the output JSON.
- **Starting slide** — the active slide at audio-start is automatically recorded at
  `t = 0.0` in both modes.
- **slide-label invariant** — `stop_time[X][-1]` always equals `start_time[X+1][-1]`;
  a single keypress appends the same timestamp to both lists simultaneously.
- **slide-label end fallback** — if the session ends before the last active slide
  receives a stop time, `build_output()` appends the audio duration automatically.
- **Multiple triggers** — revisiting a slide appends a new timestamp to the list rather
  than overwriting, preserving all training events.
- **Untriggered slides** — slides never reached by the trainer have no timing keys
  in the output JSON.
- **Audio device** — startup prints the output device name; `--device` overrides the
  system default. If `sd.play()` raises, a clear error is shown with remediation hint.
- **Playback precision** — `PlaybackSession` sleeps to within 50 ms of each cue time
  then busy-polls the remainder, achieving ~1 ms accuracy for slide trigger replay.

## Project conventions

- **Python 3.11+** — native `list[...]` / `dict[...]` / `X | Y` type hints.
- **Poetry** for dependency management.  Run `poetry install` before anything.
- **No comments** unless the WHY is non-obvious.

## Running the project

```bash
# Install deps
poetry install

# trigger-label mode (default) — records when each slide is cued
poetry run propresenter-train audio/sermon.wav "Sunday Sermon"

# slide-label mode — records audio start/stop boundaries per slide
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --mode slide-label

# JSON lands in ./output/ by default; override with --output-dir
poetry run propresenter-train audio/pledge.wav "Pledge of Allegiance" --output-dir sessions/

# Skip activating the presentation (if already active in ProPresenter)
poetry run propresenter-train audio/service.wav "Service" --no-activate

# Specify audio output device
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --device 0

# Remote ProPresenter host
poetry run propresenter-train audio/worship.wav "Worship" --host 192.168.1.10

# Search a non-default library
poetry run propresenter-train audio/song.wav "Amazing Grace" --library Songs

# Play back a gold-copy JSON to evaluate timing quality
poetry run propresenter-train-playback output/sermon.json
poetry run propresenter-train-playback output/sermon.json --no-activate --device 1
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

### trigger-label mode

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
          {"enabled": true, "notes": "", "trigger time": [0.0],   "text": "Opening words", "label": ""},
          {"enabled": true, "notes": "", "trigger time": [12.43], "text": "Second slide",  "label": ""}
        ]
      }
    ]
  }
}
```

### slide-label mode

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
          {"enabled": true, "notes": "", "start time": [0.0],   "stop time": [12.43], "text": "Opening words", "label": ""},
          {"enabled": true, "notes": "", "start time": [12.43], "stop time": [28.7],  "text": "Second slide",  "label": ""}
        ]
      }
    ]
  }
}
```

The file is written to `<output-dir>/<presentation-name>.json`.
Characters illegal on any OS (`\ / : * ? " < > |`) are replaced with `_`.
