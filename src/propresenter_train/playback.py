"""
Playback engine for propresenter-train-playback.

Reads a gold-copy JSON produced by propresenter-train, extracts slide cue
timestamps, plays back the audio, and fires slide triggers in ProPresenter
at the recorded times so the user can evaluate how well the timings work.

Timing key auto-detection order: "start time" (slide-label) then "trigger time"
(trigger-label).  All timestamps in each list are replayed in chronological order,
so slides triggered or labelled multiple times during training fire multiple times
during playback.
"""

import time
from pathlib import Path
from typing import Optional

import sounddevice as sd
import soundfile as sf

from propresenter_client.main import ProPresenterController
from presenter_json import (
    cues as _presenter_cues,
    detect_timing_key,
    from_api_response,
    load_presentation,
)


def load_cues(data: dict) -> tuple[str, list[tuple[float, int]]]:
    """
    Extract sorted (timestamp, 1-based slide number) cues from a gold-copy dict.

    Returns (timing_key_used, cue_list) where cue_list is sorted by timestamp.
    Raises ValueError if no timing data is found.
    """
    model = from_api_response(data)
    timing_key = detect_timing_key(model)
    if timing_key is None:
        raise ValueError(
            "No timing data found in JSON. "
            "Expected 'start time' (slide-label) or 'trigger time' (trigger-label)."
        )
    result = [(c.time, c.slide_index + 1) for c in _presenter_cues(model, timing_key=timing_key)]
    return timing_key, result


class PlaybackSession:
    """Fires slide triggers in ProPresenter in sync with a training audio file."""

    def __init__(
        self,
        controller: ProPresenterController,
        json_path: Path,
        device: int | None = None,
    ):
        self.controller = controller
        self.json_path = json_path
        self.device = device

        self._model = load_presentation(json_path)

        if not self._model.presentation.id.audio_path:
            raise ValueError("JSON does not contain presentation.id.audio_path")

        audio_path = Path(self._model.presentation.id.audio_path)
        if not audio_path.is_absolute():
            audio_path = json_path.parent / audio_path
        self.audio_path = audio_path
        if not self.audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {self.audio_path}")

        self.timing_key = detect_timing_key(self._model)
        if self.timing_key is None:
            raise ValueError(
                "No timing data found in JSON. "
                "Expected 'start time' (slide-label) or 'trigger time' (trigger-label)."
            )
        self.cues = [(c.time, c.slide_index + 1) for c in _presenter_cues(self._model, timing_key=self.timing_key)]

    @property
    def presentation_name(self) -> str:
        return self._model.presentation.id.name or "Unknown"

    @property
    def presentation_uuid(self) -> Optional[str]:
        return self._model.presentation.id.uuid

    @staticmethod
    def _fmt_time(t: float) -> str:
        mins = int(t // 60)
        secs = t % 60
        return f"{mins:02d}:{secs:05.2f}"

    def run(self, early_trigger_window: float = 0.2) -> None:
        """Play audio and fire slide triggers at recorded timestamps.

        early_trigger_window: seconds before the recorded cue time to fire the trigger.
                              Compensates for ProPresenter slide rendering latency.
        """
        audio_data, samplerate = sf.read(str(self.audio_path), dtype="float32")
        duration = len(audio_data) / samplerate

        try:
            dev_name = sd.query_devices(device=self.device, kind="output")["name"]
        except Exception:
            dev_name = "unknown"

        print(f"\nPresentation : {self.presentation_name}")
        print(f"Audio        : {self.audio_path}  ({self._fmt_time(duration)})")
        print(f"Device       : {dev_name}")
        print(f"Timing key   : {self.timing_key}")
        print(f"Cues         : {len(self.cues)}")
        print(f"Window       : {early_trigger_window * 1000:.0f} ms early")
        print("\nPress Ctrl+C to stop.\n")

        try:
            sd.play(audio_data, samplerate, device=self.device)
        except Exception as e:
            print(f"Error: Could not start audio playback: {e}")
            raise

        t0 = time.perf_counter()

        try:
            for timestamp, slide_num in self.cues:
                fire_at = max(0.0, timestamp - early_trigger_window)
                # Sleep to within 50 ms of the fire time, then busy-poll the remainder
                # so the trigger fires within ~1 ms of the target.
                sleep_for = fire_at - (time.perf_counter() - t0) - 0.05
                if sleep_for > 0:
                    time.sleep(sleep_for)
                while time.perf_counter() - t0 < fire_at:
                    pass

                actual = time.perf_counter() - t0
                ok = self.controller.go_to_slide(slide_num)
                drift_ms = (actual - timestamp) * 1000
                status = "" if ok else "  [TRIGGER FAILED]"
                print(
                    f"  Slide {slide_num:>3}  "
                    f"cue +{self._fmt_time(timestamp)}  "
                    f"fired +{self._fmt_time(actual)}  "
                    f"({drift_ms:+.1f} ms){status}"
                )

            remaining = duration - (time.perf_counter() - t0)
            if remaining > 0:
                print(f"\nAll cues fired — waiting for audio to finish...")
                time.sleep(remaining)

        except KeyboardInterrupt:
            raise
        finally:
            sd.stop()
