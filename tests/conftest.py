import pytest

from travel_agent.services import DuffelClient, SearchCache


@pytest.fixture
def duffel_client() -> DuffelClient:
    return DuffelClient(api_key="test-key", base_url="https://api.duffel.com", api_version="v2")


@pytest.fixture
def cache() -> SearchCache:
    return SearchCache(ttl_seconds=60)
