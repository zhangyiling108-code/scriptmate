from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from cmm.models import AnalysisResult, DraftResult, MatchedSegment, VideoSource


class BaseAssembler(ABC):
    @abstractmethod
    async def build(
        self,
        matched_segments: List[MatchedSegment],
        analysis: AnalysisResult,
        output_dir: str,
        source_video: Optional[VideoSource] = None,
    ) -> DraftResult:
        raise NotImplementedError
