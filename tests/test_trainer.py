"""Unit tests for TrainingSession — no audio hardware, no ProPresenter server."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from propresenter_train.models import METHOD_MANUAL
from propresenter_train.trainer import (
    MODE_SLIDE_LABEL,
    MODE_TRIGGER_LABEL,
    TrainingSession,
)


PRESENTATION_DETAILS = {
    "presentation": {
        "id": {
            "uuid": "7A465FF0-FF42-4785-82F1-5CF0DC136BAE",
            "name": "Test Presentation",
            "index": 0,
        },
        "groups": [
            {
                "name": "Group 1",
                "color": None,
                "slides": [
                    {"enabled": True, "notes": "", "text": "Slide one", "label": ""},
                    {"enabled": True, "notes": "", "text": "Slide two", "label": ""},
                    {"enabled": True, "notes": "", "text": "Slide three", "label": ""},
                ],
            }
        ],
    }
}


def _make_session(mode: str = MODE_TRIGGER_LABEL) -> TrainingSession:
    controller = MagicMock()
    controller.get_slide_index.return_value = 0
    controller.next_slide.return_value = True
    controller.previous_slide.return_value = True
    controller.go_to_slide.return_value = True
    return TrainingSession(
        controller=controller,
        presentation_details=PRESENTATION_DETAILS,
        audio_path=Path("audio/test.wav"),
        mode=mode,
    )


class TestSlideCount:
    def test_counts_all_slides(self):
        assert _make_session()._total_slides == 3


class TestTriggerLabelMode:
    def test_audio_injected_into_id(self):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._trigger_times = {0: [0.0], 1: [2.5], 2: [5.1]}

        output = session.build_output()
        assert output["presentation"]["id"]["audio"] == "audio/test.wav"

    def test_url_and_method_injected_into_id(self):
        session = _make_session()
        session._session_start = time.perf_counter()

        output = session.build_output()
        id_obj = output["presentation"]["id"]
        assert id_obj["url"] == ""
        assert id_obj["method"] == METHOD_MANUAL

    def test_custom_url_and_method(self):
        controller = MagicMock()
        controller.get_slide_index.return_value = 0
        session = TrainingSession(
            controller=controller,
            presentation_details=PRESENTATION_DETAILS,
            audio_path=Path("audio/test.wav"),
            mode=MODE_TRIGGER_LABEL,
            url="https://youtu.be/abc123",
            method="captions",
        )
        session._session_start = time.perf_counter()

        output = session.build_output()
        id_obj = output["presentation"]["id"]
        assert id_obj["url"] == "https://youtu.be/abc123"
        assert id_obj["method"] == "captions"

    def test_trigger_times_are_lists(self):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._trigger_times = {0: [0.0], 1: [2.5]}

        slides = session.build_output()["presentation"]["groups"][0]["slides"]
        assert slides[0]["trigger time"] == [0.0]
        assert slides[1]["trigger time"] == [2.5]
        assert "trigger time" not in slides[2]

    def test_multiple_triggers_on_same_slide(self):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._trigger_times = {0: [0.0, 3.1]}

        slides = session.build_output()["presentation"]["groups"][0]["slides"]
        assert slides[0]["trigger time"] == [0.0, 3.1]

    def test_untriggered_slides_have_no_key(self):
        session = _make_session()
        session._session_start = time.perf_counter()

        for slide in session.build_output()["presentation"]["groups"][0]["slides"]:
            assert "trigger time" not in slide

    def test_does_not_mutate_original(self):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._trigger_times = {0: [1.0]}

        session.build_output()
        assert "trigger time" not in PRESENTATION_DETAILS["presentation"]["groups"][0]["slides"][0]

    def test_cmd_next_appends_trigger_time(self):
        session = _make_session()
        session._session_start = time.perf_counter() - 5.0
        session._current_index = 0

        session._cmd_next()
        assert session._current_index == 1
        assert len(session._trigger_times[1]) == 1
        assert session._trigger_times[1][0] >= 5.0

    def test_cmd_next_twice_appends_second_trigger(self):
        session = _make_session()
        session._session_start = time.perf_counter() - 5.0
        session._current_index = 0
        session._trigger_times = {1: [1.0]}  # slide 1 already triggered once

        session._cmd_next()  # triggers slide 1 again (going back and forward)
        # _cmd_next increments index to 1, so this goes 0->1
        assert len(session._trigger_times[1]) == 2

    def test_cmd_back_records_trigger_time(self):
        session = _make_session()
        session._session_start = time.perf_counter() - 3.0
        session._current_index = 2

        session._cmd_back()
        assert session._current_index == 1
        assert 1 in session._trigger_times

    def test_cmd_next_at_last_slide_does_nothing(self):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._current_index = 2

        session._cmd_next()
        assert session._current_index == 2

    def test_cmd_back_at_first_slide_does_nothing(self):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._current_index = 0

        session._cmd_back()
        assert session._current_index == 0


class TestSlideLabelMode:
    def test_start_and_stop_are_lists(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter()
        session._start_times = {0: [0.0], 1: [3.2]}
        session._stop_times = {0: [3.2], 1: [7.8]}

        slides = session.build_output()["presentation"]["groups"][0]["slides"]
        assert slides[0]["start time"] == [0.0]
        assert slides[0]["stop time"] == [3.2]
        assert slides[1]["start time"] == [3.2]
        assert slides[1]["stop time"] == [7.8]
        assert "start time" not in slides[2]
        assert "stop time" not in slides[2]

    def test_multiple_boundaries_on_same_slide(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter()
        session._start_times = {0: [0.0, 5.0]}
        session._stop_times = {0: [3.2, 8.1]}

        slides = session.build_output()["presentation"]["groups"][0]["slides"]
        assert slides[0]["start time"] == [0.0, 5.0]
        assert slides[0]["stop time"] == [3.2, 8.1]

    def test_no_trigger_time_key_in_slide_label_mode(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter()
        session._start_times = {0: [0.0]}
        session._stop_times = {0: [5.0]}

        for slide in session.build_output()["presentation"]["groups"][0]["slides"]:
            assert "trigger time" not in slide

    def test_cmd_next_appends_stop_and_start(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter() - 4.0
        session._current_index = 0

        session._cmd_next()

        assert session._current_index == 1
        assert len(session._stop_times[0]) == 1
        assert len(session._start_times[1]) == 1
        assert session._stop_times[0][0] == session._start_times[1][0]

    def test_cmd_next_appends_on_revisit(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter() - 4.0
        session._current_index = 0
        session._stop_times = {0: [2.0]}
        session._start_times = {1: [2.0]}

        session._cmd_next()  # visit 0->1 again

        assert len(session._stop_times[0]) == 2
        assert len(session._start_times[1]) == 2

    def test_cmd_back_appends_stop_and_start(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter() - 6.0
        session._current_index = 2

        session._cmd_back()

        assert session._current_index == 1
        assert 1 in session._stop_times
        assert 2 in session._start_times
        assert session._stop_times[1][0] == session._start_times[2][0]

    def test_cmd_goto_appends_stop_on_current_and_start_on_target(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter() - 2.0
        session._current_index = 0

        session._cmd_goto("3")

        assert session._current_index == 2
        assert 0 in session._stop_times
        assert 2 in session._start_times
        assert session._stop_times[0][0] == session._start_times[2][0]

    def test_last_slide_stop_filled_with_audio_duration(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter()
        session._audio_duration = 30.0
        session._current_index = 2
        session._start_times = {0: [0.0], 1: [10.0], 2: [20.0]}
        session._stop_times = {0: [10.0], 1: [20.0]}

        slides = session.build_output()["presentation"]["groups"][0]["slides"]
        assert slides[2]["stop time"] == [30.0]

    def test_stop_time_appended_not_overwritten_by_audio_duration(self):
        session = _make_session(MODE_SLIDE_LABEL)
        session._session_start = time.perf_counter()
        session._audio_duration = 30.0
        session._current_index = 1
        session._start_times = {0: [0.0], 1: [10.0]}
        session._stop_times = {0: [10.0], 1: [18.5]}

        slides = session.build_output()["presentation"]["groups"][0]["slides"]
        assert slides[1]["stop time"] == [18.5]


class TestSave:
    def test_writes_json_file(self, tmp_path):
        session = _make_session()
        session._session_start = time.perf_counter()
        session._trigger_times = {0: [0.0], 1: [3.7]}

        out = session.save(tmp_path)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["presentation"]["id"]["name"] == "Test Presentation"

    def test_filename_matches_presentation_name(self, tmp_path):
        session = _make_session()
        session._session_start = time.perf_counter()

        out = session.save(tmp_path)
        assert out.name == "Test Presentation.json"

    def test_illegal_chars_replaced_in_filename(self, tmp_path):
        session = _make_session()
        session.presentation_details = {
            "presentation": {
                "id": {"uuid": "x", "name": "A/B:C*D", "index": 0},
                "groups": [{"slides": []}],
            }
        }
        session._total_slides = 0
        session._session_start = time.perf_counter()

        out = session.save(tmp_path)
        assert "/" not in out.name
        assert ":" not in out.name


class TestElapsed:
    def test_zero_before_start(self):
        assert _make_session().elapsed() == 0.0

    def test_positive_after_start(self):
        session = _make_session()
        session._session_start = time.perf_counter() - 1.0
        assert session.elapsed() >= 1.0
