"""Hotel search tool, backed by the Duffel Stays API (free test mode).

Replaces the Amadeus-backed version. Duffel Stays searches by geographic
coordinates + a radius rather than a city/IATA code, so this tool resolves
a city name to coordinates first. `_CITY_COORDS` is a small, explicit
lookup table — a pragmatic stand-in for a real geocoding service (Mapbox,
Google, etc.), which is what Duffel's own docs recommend for full city
coverage. Cities outside the table return a clear, typed "unsupported"
message instead of guessing or crashing.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from travel_agent.services import DuffelAPIError, DuffelClient, SearchCache, make_cache_key

logger = logging.getLogger(__name__)

# city name (lowercased) -> (latitude, longitude). Extend as needed, or
# replace with a real geocoding call for full coverage.
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "new york": (40.7128, -74.0060),
    "london": (51.5072, -0.1276),
    "paris": (48.8566, 2.3522),
    "tokyo": (35.6762, 139.6503),
    "madrid": (40.4168, -3.7038),
    "rome": (41.9028, 12.4964),
    "amsterdam": (52.3676, 4.9041),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "los angeles": (34.0522, -118.2437),
    "san francisco": (37.7749, -122.4194),
    "chicago": (41.8781, -87.6298),
    "toronto": (43.6532, -79.3832),
    "sydney": (-33.8688, 151.2093),
    "bali": (-8.3405, 115.0920),
    "zurich": (47.3769, 8.5417),
    "bangkok": (13.7563, 100.5018),
    "hong kong": (22.3193, 114.1694),
    "berlin": (52.5200, 13.4050),
    "varanasi": (25.3176, 82.9739),
}

_SEARCH_RADIUS_KM = 15


class HotelsInput(BaseModel):
    city: str = Field(description="Destination city name, e.g. 'New York', 'Paris'")
    check_in_date: str = Field(description="Check-in date, format YYYY-MM-DD")
    check_out_date: str = Field(description="Check-out date, format YYYY-MM-DD")
    adults: int = Field(1, description="Number of adults")
    room_quantity: int = Field(1, description="Number of rooms")
    max_results: int = Field(5, description="Max number of hotel results to return")
    hotel_class: str | None = Field(None, description="Not currently filtered on — kept for prompt compatibility.")


class HotelsInputSchema(BaseModel):
    params: HotelsInput


def _summarize_stay_result(entry: dict) -> dict:
    accommodation = entry.get("accommodation", {})
    return {
        "name": accommodation.get("name"),
        "rating": accommodation.get("rating"),
        "city": accommodation.get("location", {}).get("address", {}).get("city_name"),
        "price": entry.get("cheapest_rate_total_amount"),
        "currency": entry.get("cheapest_rate_currency"),
        "room_type": None,  # room-level detail requires a follow-up fetch_all_rates call; out of scope for a search summary
        "offer_count": entry.get("rooms"),
    }


def build_hotels_tool(client: DuffelClient, cache: SearchCache):
    """Factory mirroring build_flights_tool — see that module for the rationale."""

    @tool(args_schema=HotelsInputSchema)
    def hotels_finder(params: HotelsInput):
        """Find hotels in a city for given check-in/check-out dates. Returns a list of
        hotel results with name, star rating, and cheapest available price."""
        cache_key = make_cache_key(tool="hotels", **params.model_dump())
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info("Hotel search cache hit for %s", params.city)
            return cached

        coords = _CITY_COORDS.get(params.city.strip().lower())
        if not coords:
            return {
                "message": f"'{params.city}' isn't in the supported city list yet. "
                f"Try a major city name, or extend _CITY_COORDS with real geocoding."
            }
        latitude, longitude = coords

        request_body = {
            "data": {
                "location": {"geographic_coordinates": {"latitude": latitude, "longitude": longitude}, "radius": _SEARCH_RADIUS_KM},
                "check_in_date": params.check_in_date,
                "check_out_date": params.check_out_date,
                "guests": [{"type": "adult"} for _ in range(params.adults)],
                "rooms": params.room_quantity,
            }
        }
        try:
            raw = client.post("/stays/search", request_body)
        except DuffelAPIError as exc:
            logger.warning("Hotel search failed: %s", exc)
            return {"error": "Hotel search is temporarily unavailable. Please try again shortly."}

        results = [_summarize_stay_result(entry) for entry in raw.get("data", {}).get("results", [])]
        results.sort(key=lambda r: float(r["price"]) if r["price"] else float("inf"))
        results = results[: params.max_results] or {"message": "No hotel results available for these dates."}

        cache.set(cache_key, results)
        return results

    return hotels_finder
