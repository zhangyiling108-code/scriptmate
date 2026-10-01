"""Provider construction is centralized so search routing stays independent of sources."""
from cmm.fetcher.commons import CommonsProvider
from cmm.fetcher.coverr import CoverrProvider
from cmm.fetcher.nasa import NasaImagesProvider
from cmm.fetcher.openverse import OpenverseProvider
from cmm.fetcher.pexels import PexelsProvider
from cmm.fetcher.pixabay import PixabayProvider


PROVIDER_FACTORIES = {
    "pexels": lambda sources, matching: PexelsProvider(sources.pexels.api_key, matching),
    "pixabay": lambda sources, matching: PixabayProvider(sources.pixabay.api_key, matching),
    "coverr": lambda sources, matching: CoverrProvider(sources.coverr.api_key, matching, sources.coverr.base_url),
    "nasa": lambda sources, matching: NasaImagesProvider(matching, sources.nasa.base_url),
    "openverse": lambda sources, matching: OpenverseProvider(sources.openverse, matching),
    "commons": lambda sources, matching: CommonsProvider(sources.commons, matching),
}


def build_providers(sources, matching):
    unknown = set(sources.enabled) - PROVIDER_FACTORIES.keys()
    if unknown:
        raise ValueError("Unknown built-in sources: " + ", ".join(sorted(unknown)) + ". Use sources.extra for manual libraries.")
    return {name: factory(sources, matching) for name, factory in PROVIDER_FACTORIES.items()}
