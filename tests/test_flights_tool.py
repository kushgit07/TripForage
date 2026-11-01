from travel_agent.services import DuffelAPIError, SearchCache
from travel_agent.tools.flights import FlightsInput, build_flights_tool

SAMPLE_OFFER = {
    "total_amount": "702.00",
    "total_currency": "USD",
    "available_seats": 4,
    "slices": [
        {
            "duration": "PT8H",
            "segments": [
                {
                    "operating_carrier": {"name": "American Airlines"},
                    "operating_carrier_flight_number": "100",
                    "origin": {"iata_code": "MAD"},
                    "departing_at": "2026-10-01T10:25:00",
                    "destination": {"iata_code": "JFK"},
                    "arriving_at": "2026-10-01T12:25:00",
                    "duration": "PT8H",
                }
            ],
        }
    ],
}


class FakeDuffelClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.call_count = 0

    def post(self, path, json_body, params=None):
        self.call_count += 1
        if self.error:
            raise self.error
        return self.response


def _params() -> dict:
    return dict(
        params=FlightsInput(
            departure_airport="MAD", arrival_airport="JFK", outbound_date="2026-10-01", return_date="2026-10-07"
        )
    )


def test_flights_finder_summarizes_offers():
    client = FakeDuffelClient(response={"data": {"offers": [SAMPLE_OFFER]}})
    tool = build_flights_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params())

    assert result[0]["price"] == "702.00"
    assert result[0]["itineraries"][0]["segments"][0]["carrier"] == "American Airlines"


def test_flights_finder_caches_identical_queries():
    client = FakeDuffelClient(response={"data": {"offers": [SAMPLE_OFFER]}})
    tool = build_flights_tool(client, SearchCache(ttl_seconds=60))

    tool.invoke(_params())
    tool.invoke(_params())

    assert client.call_count == 1  # second call served from cache


def test_flights_finder_handles_no_results():
    client = FakeDuffelClient(response={"data": {"offers": []}})
    tool = build_flights_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params())

    assert "message" in result


def test_flights_finder_handles_api_error_gracefully():
    client = FakeDuffelClient(error=DuffelAPIError("boom"))
    tool = build_flights_tool(client, SearchCache(ttl_seconds=60))

    result = tool.invoke(_params())

    assert "error" in result
