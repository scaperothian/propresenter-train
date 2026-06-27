"""Unit tests for the playback module — no audio hardware, no ProPresenter server."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from propresenter_train.playback import PlaybackSession, load_cues


TRIGGER_LABEL_DATA = {
    "presentation": {
        "id": {
            "uuid": "AAA",
            "name": "Test Show",
            "index": 0,
            "audio": "audio/test.wav",
        },
        "groups": [
            {
                "slides": [
                    {"text": "Slide 1", "trigger time": [0.0, 5.0]},
                    {"text": "Slide 2", "trigger time": [10.0]},
                    {"text": "Slide 3"},  # no timing
                ]
            }
        ],
    }
}

SLIDE_LABEL_DATA = {
    "presentation": {
        "id": {
            "uuid": "BBB",
            "name": "Boundary Show",
            "index": 0,
            "audio": "audio/test.wav",
        },
        "groups": [
            {
                "slides": [
                    {"text": "Slide 1", "start time": [0.0], "stop time": [8.0]},
                    {"text": "Slide 2", "start time": [8.0], "stop time": [20.0]},
                ]
            }
        ],
    }
}


class TestLoadCues:
    def test_trigger_label_extracts_all_timestamps(self):
        key, cues = load_cues(TRIGGER_LABEL_DATA)
        assert key == "trigger time"
        # slide 1 has [0.0, 5.0], slide 2 has [10.0], slide 3 has nothing
        assert len(cues) == 3
        assert cues == [(0.0, 1), (5.0, 1), (10.0, 2)]

    def test_slide_label_uses_start_time(self):
        key, cues = load_cues(SLIDE_LABEL_DATA)
        assert key == "start time"
        assert cues == [(0.0, 1), (8.0, 2)]

    def test_cues_sorted_by_timestamp(self):
        data = {
            "presentation": {
                "id": {},
                "groups": [
                    {
                        "slides": [
                            {"trigger time": [5.0, 1.0]},
                            {"trigger time": [3.0]},
                        ]
                    }
                ],
            }
        }
        _, cues = load_cues(data)
        timestamps = [t for t, _ in cues]
        assert timestamps == sorted(timestamps)

    def test_no_timing_data_raises(self):
        data = {
            "presentation": {
                "groups": [{"slides": [{"text": "no timing"}]}]
            }
        }
        with pytest.raises(ValueError, match="No timing data"):
            load_cues(data)

    def test_slide_label_preferred_over_trigger_label(self):
        data = {
            "presentation": {
                "groups": [
                    {
                        "slides": [
                            {"start time": [0.0], "trigger time": [0.5]},
                        ]
                    }
                ]
            }
        }
        key, _ = load_cues(data)
        assert key == "start time"

    def test_untimed_slides_are_skipped(self):
        _, cues = load_cues(TRIGGER_LABEL_DATA)
        slide_nums = [s for _, s in cues]
        assert 3 not in slide_nums


class TestPlaybackSession:
    def _make_session(self, data: dict, audio_exists: bool = True) -> PlaybackSession:
        controller = MagicMock()
        tmp_json = Path("/tmp/test_playback.json")
        tmp_json.write_text(json.dumps(data))

        with patch("propresenter_train.playback.Path.is_file", return_value=audio_exists):
            session = PlaybackSession(controller=controller, json_path=tmp_json)
        return session

    def test_presentation_name(self):
        session = self._make_session(TRIGGER_LABEL_DATA)
        assert session.presentation_name == "Test Show"

    def test_presentation_uuid(self):
        session = self._make_session(TRIGGER_LABEL_DATA)
        assert session.presentation_uuid == "AAA"

    def test_audio_path_extracted(self):
        session = self._make_session(TRIGGER_LABEL_DATA)
        # relative path in JSON is resolved against the JSON file's directory (/tmp)
        assert session.audio_path == Path("/tmp") / "audio/test.wav"

    def test_absolute_audio_path_unchanged(self):
        data = {
            "presentation": {
                "id": {"uuid": "X", "name": "Y", "audio": "/absolute/path/song.wav"},
                "groups": [{"slides": [{"trigger time": [1.0]}]}],
            }
        }
        session = self._make_session(data)
        assert session.audio_path == Path("/absolute/path/song.wav")

    def test_missing_audio_key_raises(self):
        data = {
            "presentation": {
                "id": {"uuid": "X", "name": "Y"},
                "groups": [{"slides": [{"trigger time": [1.0]}]}],
            }
        }
        controller = MagicMock()
        tmp_json = Path("/tmp/test_no_audio.json")
        tmp_json.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="presentation.id.audio"):
            PlaybackSession(controller=controller, json_path=tmp_json)

    def test_missing_audio_file_raises(self):
        controller = MagicMock()
        tmp_json = Path("/tmp/test_missing_audio.json")
        tmp_json.write_text(json.dumps(TRIGGER_LABEL_DATA))
        with pytest.raises(FileNotFoundError):
            PlaybackSession(controller=controller, json_path=tmp_json)

    def test_cues_loaded(self):
        session = self._make_session(TRIGGER_LABEL_DATA)
        assert len(session.cues) == 3
        assert session.timing_key == "trigger time"
