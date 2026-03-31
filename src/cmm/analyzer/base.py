from __future__ import annotations

from abc import ABC, abstractmethod

from cmm.models import AnalysisResult


class BaseAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, text: str, aspect: str) -> AnalysisResult:
        raise NotImplementedError
