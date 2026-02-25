from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PresenceConditionExtractor import PresenceConditionExtractor
from source_loader import load_source_code
from source_path_service import resolve_existing_source_path


@dataclass(frozen=True)
class PipelineServices:
    resolve_existing_source_path: Callable[[str, str, str], str]
    load_source_code: Callable[[str], str]
    build_extractor: Callable[[str], PresenceConditionExtractor]


def default_pipeline_services() -> PipelineServices:
    return PipelineServices(
        resolve_existing_source_path=resolve_existing_source_path,
        load_source_code=load_source_code,
        build_extractor=PresenceConditionExtractor,
    )
