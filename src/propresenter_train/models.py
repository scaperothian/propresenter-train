"""
Pydantic models for the propresenter-train gold-copy JSON format.

The top-level shape mirrors the /v1/presentation/{uuid} ProPresenter API response
with extra keys added to presentation.id (audio, url, method, version).

All ProPresenter API fields not explicitly modelled here pass through via
extra="allow" so the output JSON faithfully reflects the original API response.
Timing fields (trigger time, start time, stop time) are stored as extras on Slide
so they are omitted entirely from slides that were never triggered.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

METHOD_MANUAL = "manual"
METHOD_CAPTIONS = "captions"
METHOD_MODEL = "model"


class PresentationId(BaseModel):
    model_config = ConfigDict(extra="allow")

    uuid: str | None = None
    name: str | None = None
    index: int | None = None
    audio: str = ""
    url: str = ""
    method: str = METHOD_MANUAL
    version: str = ""


class Slide(BaseModel):
    """A single ProPresenter slide. All fields (enabled, notes, text, label, …) pass
    through as extras. Timing keys are written directly into model_extra so they appear
    in the output only for slides that were actually triggered."""

    model_config = ConfigDict(extra="allow")


class Group(BaseModel):
    model_config = ConfigDict(extra="allow")

    slides: list[Slide] = Field(default_factory=list)


class Presentation(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: PresentationId = Field(default_factory=PresentationId)
    groups: list[Group] = Field(default_factory=list)


class PresentationFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    presentation: Presentation
