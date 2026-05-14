"""Unit tests for TrainingSession — no audio hardware, no ProPresenter server."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from propresenter_train.trainer import TrainingSession


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


def _make_session() -> TrainingSession:
    controller = MagicMock()
    controller.get_slide_index.return_value = 0
    controller.next_slide.return_value = True
    controller.previous_slide.return_value = True
    controller.go_to_slide.return_value = True
    return TrainingSession(
        controller=controller,
        presentation_details=PRESENTATION_DETAILS,
        audio_path=Path("audio/test.wav"),
    )


class TestSlideCount:
    def test_counts_all_slides(self):
        session = _make_session()
        assert session._total_slides == 3


class TestBuildOutput:
    def test_audio_injected_into_id(self):
        session = _make_session()
        session._start_time = time.perf_counter()
        session._trigger_times = {0: 0.0, 1: 2.5, 2: 5.1}

        output = session.build_output()
        assert output["presentation"]["id"]["audio"] == "audio/test.wav"

    def test_trigger_times_injected_into_slides(self):
        session = _make_session()
        session._start_time = time.perf_counter()
        session._trigger_times = {0: 0.0, 1: 2.5}

        output = session.build_output()
        slides = output["presentation"]["groups"][0]["slides"]
        assert slides[0]["trigger time"] == 0.0
        assert slides[1]["trigger time"] == 2.5
        assert "trigger time" not in slides[2]

    def test_does_not_mutate_original(self):
        session = _make_session()
        session._start_time = time.perf_counter()
        session._trigger_times = {0: 1.0}

        session.build_output()
        assert "trigger time" not in PRESENTATION_DETAILS["presentation"]["groups"][0]["slides"][0]

    def test_untriggered_slides_have_no_key(self):
        session = _make_session()
        session._start_time = time.perf_counter()
        session._trigger_times = {}

        output = session.build_output()
        for slide in output["presentation"]["groups"][0]["slides"]:
            assert "trigger time" not in slide


class TestSave:
    def test_writes_json_file(self, tmp_path):
        session = _make_session()
        session._start_time = time.perf_counter()
        session._trigger_times = {0: 0.0, 1: 3.7}

        out = session.save(tmp_path)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["presentation"]["id"]["name"] == "Test Presentation"

    def test_filename_matches_presentation_name(self, tmp_path):
        session = _make_session()
        session._start_time = time.perf_counter()
        session._trigger_times = {}

        out = session.save(tmp_path)
        assert out.name == "Test Presentation.json"

    def test_illegal_chars_replaced_in_filename(self, tmp_path):
        session = _make_session()
        session.presentation_details = {
            "presentation": {
                "id": {"uuid": "x", "name": 'A/B:C*D', "index": 0},
                "groups": [{"slides": []}],
            }
        }
        session._total_slides = 0
        session._start_time = time.perf_counter()
        session._trigger_times = {}

        out = session.save(tmp_path)
        assert "/" not in out.name
        assert ":" not in out.name


class TestElapsed:
    def test_zero_before_start(self):
        session = _make_session()
        assert session.elapsed() == 0.0

    def test_positive_after_start(self):
        session = _make_session()
        session._start_time = time.perf_counter() - 1.0
        assert session.elapsed() >= 1.0
