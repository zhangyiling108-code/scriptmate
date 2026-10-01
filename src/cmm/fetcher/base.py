from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from cmm.models import MaterialCandidate, Segment


class BaseStockProvider(ABC):
    media_types = frozenset({"image", "video"})
    supports_cjk = False

    @abstractmethod
    async def search(self, segment: Segment, query: str) -> List[MaterialCandidate]:
        raise NotImplementedError
