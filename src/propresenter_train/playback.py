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

from .models import PresentationFile

_TIMING_KEY_PRIORITY = ("start time", "trigger time")


def _detect_timing_key(slides: list) -> Optional[str]:
    """Return the first timing key found across all slides, or None."""
    for key in _TIMING_KEY_PRIORITY:
        if any(isinstance(s, dict) and key in s for s in slides):
            return key
    return None


def load_cues(data: dict) -> tuple[str, list[tuple[float, int]]]:
    """
    Extract sorted (timestamp, 1-based slide number) cues from a gold-copy dict.

    Returns (timing_key_used, cue_list) where cue_list is sorted by timestamp.
    Raises ValueError if no timing data is found.
    """
    slides = ProPresenterController.find_slides(data)
    timing_key = _detect_timing_key(slides)
    if timing_key is None:
        raise ValueError(
            "No timing data found in JSON. "
            "Expected 'start time' (slide-label) or 'trigger time' (trigger-label)."
        )

    cues: list[tuple[float, int]] = []
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        values = slide.get(timing_key)
        if not isinstance(values, list):
            continue
        for t in values:
            if isinstance(t, (int, float)):
                cues.append((float(t), idx + 1))

    cues.sort(key=lambda x: x[0])
    return timing_key, cues


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

        raw = json_path.read_text()
        self._model = PresentationFile.model_validate_json(raw)

        if not self._model.presentation.id.audio:
            raise ValueError("JSON does not contain presentation.id.audio")

        self.audio_path = Path(self._model.presentation.id.audio)
        if not self.audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {self.audio_path}")

        self.timing_key, self.cues = load_cues(self._model.model_dump(by_alias=True))

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

    def run(self) -> None:
        """Play audio and fire slide triggers at recorded timestamps."""
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
        print("\nPress Ctrl+C to stop.\n")

        try:
            sd.play(audio_data, samplerate, device=self.device)
        except Exception as e:
            print(f"Error: Could not start audio playback: {e}")
            raise

        t0 = time.perf_counter()

        try:
            for timestamp, slide_num in self.cues:
                # Sleep to within 50 ms of the target, then busy-poll the remainder
                # so the trigger fires within ~1 ms of the recorded time.
                sleep_for = timestamp - (time.perf_counter() - t0) - 0.05
                if sleep_for > 0:
                    time.sleep(sleep_for)
                while time.perf_counter() - t0 < timestamp:
                    pass

                actual = time.perf_counter() - t0
                self.controller.go_to_slide(slide_num)
                drift_ms = (actual - timestamp) * 1000
                print(
                    f"  Slide {slide_num:>3}  "
                    f"target +{self._fmt_time(timestamp)}  "
                    f"actual +{self._fmt_time(actual)}  "
                    f"({drift_ms:+.1f} ms)"
                )

            remaining = duration - (time.perf_counter() - t0)
            if remaining > 0:
                print(f"\nAll cues fired — waiting for audio to finish...")
                time.sleep(remaining)

        except KeyboardInterrupt:
            raise
        finally:
            sd.stop()
