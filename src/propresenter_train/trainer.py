"""
Core training session logic.

Plays an audio file, presents an interactive slide-control prompt reusing
_get_command() from propresenter-client, and records the wall-clock offset
(relative to audio-start) at which each slide was triggered by the human
trainer.  On exit the session writes an annotated ProPresenter presentation
JSON that matches the /v1/presentation/{uuid} response shape with an extra
"trigger time" key injected into each triggered slide dict.
"""

import copy
import json
import sys
import time
from pathlib import Path
from typing import Optional

import sounddevice as sd
import soundfile as sf

from propresenter_client.main import ProPresenterController, _get_command


class TrainingSession:
    """Plays audio and records human slide-trigger times against it."""

    def __init__(
        self,
        controller: ProPresenterController,
        presentation_details: dict,
        audio_path: Path,
    ):
        self.controller = controller
        self.presentation_details = presentation_details
        self.audio_path = audio_path

        self._trigger_times: dict[int, float] = {}  # flat slide index -> seconds
        self._start_time: Optional[float] = None
        self._current_index: int = 0  # 0-based flat index of the active slide
        self._total_slides: int = len(ProPresenterController.find_slides(presentation_details))

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------

    def elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.perf_counter() - self._start_time

    @staticmethod
    def _fmt_time(t: float) -> str:
        mins = int(t // 60)
        secs = t % 60
        return f"{mins:02d}:{secs:05.2f}"

    # ------------------------------------------------------------------
    # Session entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Load audio, start playback, run the training loop, then stop."""
        data, samplerate = sf.read(str(self.audio_path), dtype="float32")
        duration = len(data) / samplerate

        print(f"\nAudio : {self.audio_path}  (duration {self._fmt_time(duration)})")
        print(f"Slides: {self._total_slides} total")
        print("\n=== ProPresenter Training Mode ===")
        print("Commands: 'n' next  'b' back  <number> go-to-slide  'q' save & quit")
        print("Trigger slide changes in sync with the audio playback.\n")

        # Seed current slide index from ProPresenter if possible
        live_idx = self.controller.get_slide_index()
        self._current_index = live_idx if live_idx is not None else 0

        # Start audio and begin the clock
        sd.play(data, samplerate)
        self._start_time = time.perf_counter()

        # The starting slide is implicitly triggered at t=0
        self._trigger_times[self._current_index] = 0.0
        print(f"  Slide {self._current_index + 1}/{self._total_slides} — starting position at +00:00.00")

        try:
            self._loop()
        finally:
            sd.stop()

    # ------------------------------------------------------------------
    # Interactive loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            t_display = self._fmt_time(self.elapsed())
            sys.stdout.write(f"[+{t_display}] command (n/b/<num>/q): ")
            sys.stdout.flush()

            cmd = _get_command()

            if cmd == "q":
                print("Saving and exiting...")
                break

            elif cmd == "n":
                if self._current_index >= self._total_slides - 1:
                    print("Already at last slide.")
                    continue
                t = self.elapsed()
                self._current_index += 1
                self._trigger_times[self._current_index] = round(t, 3)
                self.controller.next_slide()
                print(f"  -> Slide {self._current_index + 1}/{self._total_slides} at +{self._fmt_time(t)}")

            elif cmd == "b":
                if self._current_index <= 0:
                    print("Already at first slide.")
                    continue
                t = self.elapsed()
                self._current_index -= 1
                self._trigger_times[self._current_index] = round(t, 3)
                self.controller.previous_slide()
                print(f"  -> Slide {self._current_index + 1}/{self._total_slides} at +{self._fmt_time(t)}")

            else:
                try:
                    slide_num = int(cmd)
                    if slide_num < 1 or slide_num > self._total_slides:
                        print(f"Slide number must be between 1 and {self._total_slides}.")
                        continue
                    t = self.elapsed()
                    self._current_index = slide_num - 1
                    self._trigger_times[self._current_index] = round(t, 3)
                    self.controller.go_to_slide(slide_num)
                    print(f"  -> Slide {self._current_index + 1}/{self._total_slides} at +{self._fmt_time(t)}")
                except ValueError:
                    print("Unknown command. Use n, b, a slide number (1-based), or q.")

    # ------------------------------------------------------------------
    # Output construction
    # ------------------------------------------------------------------

    def build_output(self) -> dict:
        """Return an annotated deep-copy of the presentation details JSON.

        Changes versus the raw API response:
        - presentation.id.audio  — path of the training audio file
        - each triggered slide dict gains a "trigger time" key (seconds float)
        """
        output = copy.deepcopy(self.presentation_details)

        # Inject audio path into presentation.id
        pres = output.get("presentation")
        if isinstance(pres, dict):
            id_obj = pres.get("id")
            if isinstance(id_obj, dict):
                id_obj["audio"] = str(self.audio_path)

        # Walk the same traversal order as ProPresenterController.find_slides()
        # and stamp trigger times onto each slide in place.
        self._annotate(output, counter=[0])

        return output

    def _annotate(self, node: object, counter: list[int]) -> None:
        """Recursively mirror find_slides() traversal; inject 'trigger time' in place."""
        if isinstance(node, dict):
            slides = node.get("slides")
            if isinstance(slides, list):
                for slide in slides:
                    idx = counter[0]
                    if isinstance(slide, dict) and idx in self._trigger_times:
                        slide["trigger time"] = self._trigger_times[idx]
                    counter[0] += 1
                return
            for value in node.values():
                self._annotate(value, counter)
        elif isinstance(node, list):
            for item in node:
                self._annotate(item, counter)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, output_dir: Path) -> Path:
        """Write <presentation_name>.json to output_dir and return the path."""
        output = self.build_output()

        pres_name: str = "training_output"
        pres = output.get("presentation")
        if isinstance(pres, dict):
            id_obj = pres.get("id")
            if isinstance(id_obj, dict):
                pres_name = id_obj.get("name") or pres_name

        # Strip characters that are illegal in filenames on any OS
        safe_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in pres_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{safe_name}.json"

        out_path.write_text(json.dumps(output, indent=2))
        print(f"\nSaved timing data: {out_path}")
        return out_path
