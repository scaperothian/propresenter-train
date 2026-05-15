# propresenter-train

Records human slide-trigger timings against an audio file for a ProPresenter
presentation, producing a gold-copy JSON used to benchmark automated slide-cueing
systems.

## How it works

1. You provide an audio file and a presentation name already loaded in ProPresenter.
2. The tool activates the presentation, plays the audio, and gives you an interactive
   prompt identical to the standard `propresenter-client` interactive mode.
3. As the audio plays, you trigger slide changes at the right moments (`n` / `b` /
   slide number).
4. On quit the tool writes `<presentation-name>.json` — the ProPresenter presentation
   details JSON with two additions:
   - `presentation.id.audio` — path of the audio file
   - `"trigger time"` on each triggered slide — seconds since audio start

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

# Write JSON to a specific directory instead
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
| `n` | Next slide |
| `b` | Previous slide |
| `<number>` + Enter | Jump to slide N (1-indexed) |
| `q` | Save JSON and quit |
| Ctrl+C | Interrupt — saves partial results |

## Output format

The JSON file mirrors the `/v1/presentation/{uuid}` ProPresenter API response with
`"trigger time"` injected into each triggered slide:

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
          }
        ]
      }
    ]
  }
}
```

Slides not triggered by the trainer have no `"trigger time"` key.

## Running tests

```bash
poetry run pytest
```

No audio hardware or ProPresenter server required for the test suite.
