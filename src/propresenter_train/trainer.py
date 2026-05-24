"""
Core training session logic.

Supports two recording modes selected via the --mode CLI argument:

  trigger-label     (default) Records the moment the trainer advances to each slide
                    as a "trigger time" list on the slide dict.

  slide-label       Records section boundaries: a single 'next' action appends the
                    same timestamp to the "stop time" list on the current slide and
                    the "start time" list on the next slide.

All timing values are lists of floats (seconds since audio start) to support
multiple triggers per slide within a single training session.

In both modes the output JSON mirrors the /v1/presentation/{uuid} API shape and
adds presentation.id.audio with the path of the training audio file.
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

MODE_TRIGGER_LABEL = "trigger-label"
MODE_SLIDE_LABEL = "slide-label"


class TrainingSession:
    """Plays audio and records human slide timings against it."""

    def __init__(
        self,
        controller: ProPresenterController,
        presentation_details: dict,
        audio_path: Path,
        mode: str = MODE_TRIGGER_LABEL,
    ):
        self.controller = controller
        self.presentation_details = presentation_details
        self.audio_path = audio_path
        self.mode = mode

        self._trigger_times: dict[int, list[float]] = {}   # trigger-label mode
        self._start_times: dict[int, list[float]] = {}     # slide-label mode
        self._stop_times: dict[int, list[float]] = {}      # slide-label mode

        self._session_start: Optional[float] = None
        self._audio_duration: float = 0.0
        self._current_index: int = 0
        self._total_slides: int = len(ProPresenterController.find_slides(presentation_details))

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------

    def elapsed(self) -> float:
        if self._session_start is None:
            return 0.0
        return time.perf_counter() - self._session_start

    @staticmethod
    def _fmt_time(t: float) -> str:
        mins = int(t // 60)
        secs = t % 60
        return f"{mins:02d}:{secs:05.2f}"

    def _append(self, d: dict[int, list[float]], idx: int, t: float) -> None:
        d.setdefault(idx, []).append(round(t, 3))

    # ------------------------------------------------------------------
    # Session entry point
    # ------------------------------------------------------------------

    def run(self, device: int | None = None) -> None:
        """Load audio, start playback, run the training loop, then stop."""
        data, samplerate = sf.read(str(self.audio_path), dtype="float32")
        duration = len(data) / samplerate
        self._audio_duration = duration

        try:
            dev_info = sd.query_devices(device=device, kind="output")
            dev_name = dev_info["name"]
        except Exception:
            dev_name = "unknown"

        print(f"\nAudio : {self.audio_path}  (duration {self._fmt_time(duration)})")
        print(f"Device: {dev_name}")
        print(f"Slides: {self._total_slides} total")
        print(f"Mode  : {self.mode}")

        if self.mode == MODE_SLIDE_LABEL:
            print("\n=== ProPresenter Training Mode — Section Boundaries ===")
            print("Each 'n' stamps STOP on the current slide and START on the next (same timestamp).")
            print("Each 'b' stamps STOP on the previous slide and START on the current (same timestamp).")
        else:
            print("\n=== ProPresenter Training Mode — Trigger Times ===")
            print("Trigger slide changes in sync with the audio playback.")

        print("Commands: 'n' next  'b' back  <number> go-to-slide  'q' save & quit\n")

        live_idx = self.controller.get_slide_index()
        self._current_index = live_idx if live_idx is not None else 0

        try:
            sd.play(data, samplerate, device=device)
        except Exception as e:
            print(f"Error: Could not start audio playback: {e}")
            print("Check your output device with: python -m sounddevice")
            raise
        self._session_start = time.perf_counter()

        if self.mode == MODE_SLIDE_LABEL:
            self._append(self._start_times, self._current_index, 0.0)
            print(f"  Slide {self._current_index + 1}/{self._total_slides} — audio start at +00:00.00")
        else:
            self._append(self._trigger_times, self._current_index, 0.0)
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
                self._cmd_next()
            elif cmd == "b":
                self._cmd_back()
            else:
                self._cmd_goto(cmd)

    def _cmd_next(self) -> None:
        if self._current_index >= self._total_slides - 1:
            print("Already at last slide.")
            return
        t = self.elapsed()
        prev = self._current_index
        self._current_index += 1
        if self.mode == MODE_SLIDE_LABEL:
            self._append(self._stop_times, prev, t)
            self._append(self._start_times, self._current_index, t)
            self.controller.next_slide()
            print(
                f"  -> Slide {prev + 1}/{self._total_slides} stop  /  "
                f"Slide {self._current_index + 1}/{self._total_slides} start  at +{self._fmt_time(t)}"
            )
        else:
            self._append(self._trigger_times, self._current_index, t)
            self.controller.next_slide()
            print(f"  -> Slide {self._current_index + 1}/{self._total_slides} at +{self._fmt_time(t)}")

    def _cmd_back(self) -> None:
        if self._current_index <= 0:
            print("Already at first slide.")
            return
        t = self.elapsed()
        prev = self._current_index
        self._current_index -= 1
        if self.mode == MODE_SLIDE_LABEL:
            self._append(self._stop_times, self._current_index, t)
            self._append(self._start_times, prev, t)
            self.controller.previous_slide()
            print(
                f"  -> Slide {self._current_index + 1}/{self._total_slides} stop  /  "
                f"Slide {prev + 1}/{self._total_slides} start  at +{self._fmt_time(t)}"
            )
        else:
            self._append(self._trigger_times, self._current_index, t)
            self.controller.previous_slide()
            print(f"  -> Slide {self._current_index + 1}/{self._total_slides} at +{self._fmt_time(t)}")

    def _cmd_goto(self, cmd: str) -> None:
        try:
            slide_num = int(cmd)
        except ValueError:
            print("Unknown command. Use n, b, a slide number (1-based), or q.")
            return
        if slide_num < 1 or slide_num > self._total_slides:
            print(f"Slide number must be between 1 and {self._total_slides}.")
            return
        t = self.elapsed()
        prev = self._current_index
        self._current_index = slide_num - 1
        if self.mode == MODE_SLIDE_LABEL:
            self._append(self._stop_times, prev, t)
            self._append(self._start_times, self._current_index, t)
            self.controller.go_to_slide(slide_num)
            print(
                f"  -> Slide {prev + 1}/{self._total_slides} stop  /  "
                f"Slide {self._current_index + 1}/{self._total_slides} start  at +{self._fmt_time(t)}"
            )
        else:
            self._append(self._trigger_times, self._current_index, t)
            self.controller.go_to_slide(slide_num)
            print(f"  -> Slide {self._current_index + 1}/{self._total_slides} at +{self._fmt_time(t)}")

    # ------------------------------------------------------------------
    # Output construction
    # ------------------------------------------------------------------

    def build_output(self) -> dict:
        """Return an annotated deep-copy of the presentation details JSON.

        Additions versus the raw API response:
        - presentation.id.audio       — path of the training audio file
        - trigger-label mode: "trigger time" list on each triggered slide
        - slide-label mode:   "start time" and/or "stop time" lists on each labelled slide;
                              the last active slide always gets a stop time (audio duration)
                              if none was recorded before the session ended.
        """
        if self.mode == MODE_SLIDE_LABEL and self._current_index not in self._stop_times:
            self._append(self._stop_times, self._current_index, self._audio_duration)

        output = copy.deepcopy(self.presentation_details)

        pres = output.get("presentation")
        if isinstance(pres, dict):
            id_obj = pres.get("id")
            if isinstance(id_obj, dict):
                id_obj["audio"] = str(self.audio_path)

        self._annotate(output, counter=[0])
        return output

    def _annotate(self, node: object, counter: list[int]) -> None:
        """Recursively mirror find_slides() traversal; inject timing lists in place."""
        if isinstance(node, dict):
            slides = node.get("slides")
            if isinstance(slides, list):
                for slide in slides:
                    idx = counter[0]
                    if isinstance(slide, dict):
                        if self.mode == MODE_SLIDE_LABEL:
                            if idx in self._start_times:
                                slide["start time"] = self._start_times[idx]
                            if idx in self._stop_times:
                                slide["stop time"] = self._stop_times[idx]
                        else:
                            if idx in self._trigger_times:
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

        safe_name = "".join(c if c not in r'\/:*?"<>|' else "_" for c in pres_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{safe_name}.json"

        out_path.write_text(json.dumps(output, indent=2))
        print(f"\nSaved timing data: {out_path}")
        return out_path
