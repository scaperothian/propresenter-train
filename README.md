# propresenter-train

Records human slide timings against an audio file for a ProPresenter presentation,
producing a gold-copy JSON used to benchmark automated slide-cueing systems.

## Tools

| Command | Purpose |
|---------|---------|
| `propresenter-train` | Record slide timings while audio plays |
| `propresenter-train-playback` | Replay a saved JSON to evaluate timing quality |

## How it works

1. You provide an audio file and a presentation name already loaded in ProPresenter.
2. The tool activates the presentation, plays the audio, and gives you an interactive prompt.
3. As the audio plays, you control slides at the right moments (`n` / `b` / slide number + Enter).
4. On quit the tool writes `<presentation-name>.json` to `./output/` — the ProPresenter
   presentation details JSON with `presentation.id.audio` added plus per-slide timing
   keys that depend on the mode used.

## Modes

### `trigger-label` (default)

Records the moment you advance to each slide as a `"trigger time"` list on that slide.
Use this when you want to know *when* each slide was cued.

```bash
poetry run propresenter-train audio/sermon.wav "Sunday Sermon"
# or explicitly:
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --mode trigger-label
# with source URL metadata:
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --url "https://youtu.be/abc123"
```

### `slide-label`

Records audio section boundaries. Each `n` press stamps `"stop time"` on the current
slide and `"start time"` on the next slide with the same timestamp, so
`stop_time[X] == start_time[X+1]`. Use this when you want to know *which portion of
the audio* belongs to each slide.

When the session ends the last active slide's `"stop time"` is automatically filled
with the total audio duration if it was not explicitly set.

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

## propresenter-train usage

```bash
# Basic — JSON written to ./output/ by default
poetry run propresenter-train audio/sermon.wav "Sunday Sermon"

# Slide boundary labeling mode
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --mode slide-label

# Write JSON to a specific directory
poetry run propresenter-train audio/pledge.wav "Pledge of Allegiance" --output-dir sessions/

# Presentation is already active — skip the activate step
poetry run propresenter-train audio/service.wav "Service" --no-activate

# Specify audio output device (see 'python -m sounddevice' for indices)
poetry run propresenter-train audio/sermon.wav "Sunday Sermon" --device 0

# Remote ProPresenter
poetry run propresenter-train audio/worship.wav "Worship" --host 192.168.1.10

# Search a non-default library
poetry run propresenter-train audio/song.wav "Amazing Grace" --library Songs

# Attach a source URL (written to presentation.id.url)
poetry run propresenter-train audio/song.wav "Amazing Grace" --url "https://youtu.be/abc123"

# Override the timing method (manual is the default for this tool)
poetry run propresenter-train audio/song.wav "Amazing Grace" --method manual
```

## Interactive commands during training

| Key | Action |
|-----|--------|
| `n` | Next slide (fires on keypress, no Enter) |
| `b` | Previous slide (fires on keypress, no Enter) |
| `<number>` + Enter | Jump to slide N (1-indexed) |
| `q` | Save JSON and quit |
| Ctrl+C | Interrupt — saves partial results |

## propresenter-train-playback usage

Plays back the audio from a saved JSON and fires slide triggers at the recorded
timestamps, printing the target time, actual time, and drift for each cue.

```bash
# Basic — audio path is read from the JSON; presentation activated by name lookup
poetry run propresenter-train-playback output/sermon.json

# Skip activating the presentation (if already active in ProPresenter)
poetry run propresenter-train-playback output/sermon.json --no-activate

# Specify audio output device
poetry run propresenter-train-playback output/sermon.json --device 1

# Remote ProPresenter
poetry run propresenter-train-playback output/sermon.json --host 192.168.1.10

# Search a non-default library for the presentation
poetry run propresenter-train-playback output/sermon.json --library Songs

# Fire triggers 0.5 s early (compensate for rendering latency; default 0.2 s)
poetry run propresenter-train-playback output/sermon.json --early-trigger-window 0.5
```

Auto-detects timing mode from the JSON (`"start time"` for slide-label, `"trigger time"`
for trigger-label). All timestamps in each list are replayed in chronological order.

The `audio` path in the JSON can be absolute or relative. A relative path is resolved
against the directory containing the JSON file, so `song.json` with `"audio": "song.wav"`
looks for `song.wav` in the same directory as `song.json`.

## Output format

The JSON mirrors the `/v1/presentation/{uuid}` ProPresenter API response.
The following keys are always added to `presentation.id`:

| Key | Description |
|-----|-------------|
| `audio` | Path to the training audio file — absolute (`/path/to/file.wav`) or relative to the JSON file's directory (`song.wav`, `../audio/song.wav`) |
| `url` | Source URL for the audio (e.g. YouTube link); empty string if not provided |
| `method` | How timestamps were produced: `manual`, `captions`, or `model` |

Timing values are **lists of floats** (seconds since audio start), which supports
multiple triggers per slide.

### `trigger-label` output

```json
{
  "presentation": {
    "id": {
      "uuid": "7A465FF0-FF42-4785-82F1-5CF0DC136BAE",
      "name": "The Pledge of Allegiance",
      "index": 19,
      "audio": "audio/pledge_of_allegiance.wav",
      "url": "",
      "method": "manual"
    },
    "groups": [
      {
        "name": "",
        "color": null,
        "slides": [
          {
            "enabled": true,
            "notes": "",
            "trigger time": [0.32],
            "text": "I pledge allegiance to the flag",
            "label": ""
          },
          {
            "enabled": true,
            "notes": "",
            "trigger time": [4.81],
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
      "audio": "audio/pledge_of_allegiance.wav",
      "url": "",
      "method": "manual"
    },
    "groups": [
      {
        "name": "",
        "color": null,
        "slides": [
          {
            "enabled": true,
            "notes": "",
            "start time": [0.0],
            "stop time": [4.81],
            "text": "I pledge allegiance to the flag",
            "label": ""
          },
          {
            "enabled": true,
            "notes": "",
            "start time": [4.81],
            "stop time": [9.44],
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
If a slide is revisited, additional timestamps are appended to the list.

## Running tests

```bash
poetry run pytest        # all tests
poetry run pytest -v     # verbose
```

No audio hardware or ProPresenter server required for the test suite.
