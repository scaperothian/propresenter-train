# propresenter-train

Records human slide timings against an audio file for a ProPresenter presentation,
producing a gold-copy JSON used to benchmark automated slide-cueing systems.

## How it works

1. You provide an audio file and a presentation name already loaded in ProPresenter.
2. The tool activates the presentation, plays the audio, and gives you an interactive
   prompt identical to the standard `propresenter-client` interactive mode.
3. As the audio plays, you control slides at the right moments (`n` / `b` / slide number).
4. On quit the tool writes `<presentation-name>.json` — the ProPresenter presentation
   details JSON with `presentation.id.audio` added plus per-slide timing keys that
   depend on the mode used.

## Modes

### `trigger-label` (default)

Records the moment you advance to each slide as a `"trigger time"` key on that slide.
Use this when you want to know *when* each slide was cued.

```bash
poetry run propresenter-train audio/sermon.wav "Sunday Sermon"
# or explicitly:
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --mode trigger-label
```

### `slide-label`

Records audio section boundaries. Each `n` press stamps `"stop time"` on the current
slide and `"start time"` on the next slide with the same timestamp, so
`stop_time[X] == start_time[X+1]`. Use this when you want to know *which portion of
the audio* belongs to each slide.

```bash
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --mode slide-label
```

## Installation

```bash
# From the propresenter-train directory
poetry install
```

Requires Python 3.11+ and ProPresenter running locally on port 1025 (or specify
`--host` / `--port`).

## Usage

```bash
# Basic — JSON is written to ./output/ by default
poetry run propresenter-train audio/sermon.wav "Sunday Sermon"

# Slide boundary labeling mode
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --mode slide-label

# Write JSON to a specific directory
poetry run propresenter-train audio/pledge.wav "Pledge of Allegiance" --output-dir sessions/

# Presentation is already active — skip the activate step
poetry run propresenter-train audio/service.wav "Service" --no-activate

# Remote ProPresenter
poetry run propresenter-train audio/worship.wav "Worship" --host 192.168.1.10

# Search a non-default library
poetry run propresenter-train audio/song.wav "Amazing Grace" --library Songs
```

## Interactive commands

| Key | Action |
|-----|--------|
| `n` | Next slide (fires on keypress, no Enter) |
| `b` | Previous slide (fires on keypress, no Enter) |
| `<number>` + Enter | Jump to slide N (1-indexed) |
| `q` | Save JSON and quit |
| Ctrl+C | Interrupt — saves partial results |

## Output format

The JSON mirrors the `/v1/presentation/{uuid}` ProPresenter API response.
`presentation.id.audio` is always added. Timing keys depend on mode:

### `trigger-label` output

```json
{
  "presentation": {
    "id": {
      "uuid": "7A465FF0-FF42-4785-82F1-5CF0DC136BAE",
      "name": "The Pledge of Allegiance",
      "index": 19,
      "audio": "audio/pledge_of_allegiance.wav"
    },
    "groups": [
      {
        "name": "",
        "color": null,
        "slides": [
          {
            "enabled": true,
            "notes": "",
            "trigger time": 0.32,
            "text": "I pledge allegiance to the flag",
            "label": ""
          },
          {
            "enabled": true,
            "notes": "",
            "trigger time": 4.81,
            "text": "Of the United States of America",
            "label": ""
          }
        ]
      }
    ]
  }
}
```

### `slide-label` output

```json
{
  "presentation": {
    "id": {
      "uuid": "7A465FF0-FF42-4785-82F1-5CF0DC136BAE",
      "name": "The Pledge of Allegiance",
      "index": 19,
      "audio": "audio/pledge_of_allegiance.wav"
    },
    "groups": [
      {
        "name": "",
        "color": null,
        "slides": [
          {
            "enabled": true,
            "notes": "",
            "start time": 0.0,
            "stop time": 4.81,
            "text": "I pledge allegiance to the flag",
            "label": ""
          },
          {
            "enabled": true,
            "notes": "",
            "start time": 4.81,
            "stop time": 9.44,
            "text": "Of the United States of America",
            "label": ""
          }
        ]
      }
    ]
  }
}
```

Slides not reached by the trainer have no timing keys.

## Running tests

```bash
poetry run pytest
```

No audio hardware or ProPresenter server required for the test suite.
