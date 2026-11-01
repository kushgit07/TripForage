from travel_agent.services import DuffelAPIError, SearchCache
from travel_agent.tools.hotels import HotelsInput, build_hotels_tool

STAYS_SEARCH_RESPONSE = {
    "data": {
        "results": [
            {
                "accommodation": {"name": "Grand Hotel", "rating": 4, "location": {"address": {"city_name": "New York"}}},
                "cheapest_rate_total_amount": "581.00",
                "cheapest_rate_currency": "USD",
                "rooms": 1,
            },
            {
                "accommodation": {"name": "Budget Inn", "rating": 3, "location": {"address": {"city_name": "New York"}}},
                "cheapest_rate_total_amount": "199.00",
                "cheapest_rate_currency": "USD",
                "rooms": 1,
            },
        ]
    }
}


class FakeDuffelClient:
    def __init__(self, response=None, error=None):
        self.response = response if response is not None else STAYS_SEARCH_RESPONSE
        self.error = error
        self.call_count = 0

    def post(self, path, json_body):
        self.call_count += 1
        if self.error:
            raise self.error
        return self.response


def _params(city: str = "New York") -> dict:
    return dict(params=HotelsInput(city=city, check_in_date="2026-10-01", check_out_date="2026-10-07"))


def test_hotels_finder_returns_cheapest_first():
    client = FakeDuffelClient()
    tool = build_hotels_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params())

    assert result[0]["name"] == "Budget Inn"
    assert result[0]["price"] == "199.00"


def test_hotels_finder_caches_identical_queries():
    client = FakeDuffelClient()
    tool = build_hotels_tool(client, SearchCache(ttl_seconds=60))

    tool.invoke(_params())
    tool.invoke(_params())

    assert client.call_count == 1  # second call served from cache


def test_hotels_finder_handles_empty_results():
    client = FakeDuffelClient(response={"data": {"results": []}})
    tool = build_hotels_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params())

    assert "message" in result


def test_hotels_finder_handles_api_error():
    client = FakeDuffelClient(error=DuffelAPIError("boom"))
    tool = build_hotels_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params())

    assert "error" in result


def test_hotels_finder_handles_unsupported_city_without_calling_api():
    client = FakeDuffelClient()
    tool = build_hotels_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params(city="Atlantis"))

    assert "message" in result
    assert client.call_count == 0
