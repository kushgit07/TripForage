"""Flight search tool, backed by the Duffel Air API (free test mode).

Replaces the Amadeus-backed version (Amadeus's Self-Service sandbox was
decommissioned 2026-07-17). Duffel's flow is a single call: create an
"offer request" describing the trip and passengers, with `return_offers=true`
so the matching offers come back synchronously in the same response —
no separate polling step needed for a simple search like this one.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from travel_agent.services import DuffelAPIError, DuffelClient, SearchCache, make_cache_key

logger = logging.getLogger(__name__)


class FlightsInput(BaseModel):
    departure_airport: str = Field(description="Departure airport IATA code, e.g. MAD")
    arrival_airport: str = Field(description="Arrival airport IATA code, e.g. JFK")
    outbound_date: str = Field(description="Outbound date, format YYYY-MM-DD")
    return_date: str | None = Field(None, description="Return date, format YYYY-MM-DD. Omit for one-way.")
    adults: int = Field(1, description="Number of adult passengers")
    max_results: int = Field(5, description="Max number of flight offers to return")


class FlightsInputSchema(BaseModel):
    params: FlightsInput


def _summarize_offer(offer: dict) -> dict:
    """Pull out the fields the LLM actually needs, instead of Duffel's full raw offer
    payload (which includes conditions, baggage, available_services, etc.)."""
    itineraries = []
    for slice_ in offer.get("slices", []):
        segments = [
            {
                "carrier": seg.get("operating_carrier", {}).get("name") or seg.get("marketing_carrier", {}).get("name"),
                "flight_number": seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number"),
                "from": seg.get("origin", {}).get("iata_code"),
                "departure_time": seg.get("departing_at"),
                "to": seg.get("destination", {}).get("iata_code"),
                "arrival_time": seg.get("arriving_at"),
                "duration": seg.get("duration"),
            }
            for seg in slice_.get("segments", [])
        ]
        itineraries.append({"duration": slice_.get("duration"), "segments": segments})
    return {
        "price": offer.get("total_amount"),
        "currency": offer.get("total_currency"),
        "seats_available": offer.get("available_seats"),
        "itineraries": itineraries,
    }


def build_flights_tool(client: DuffelClient, cache: SearchCache):
    """Factory that closes over a configured DuffelClient/cache and returns the LangChain tool.

    Using a factory (rather than a module-level tool reading a global client) makes this
    trivially testable: tests inject a fake client instead of monkeypatching module state.
    """

    @tool(args_schema=FlightsInputSchema)
    def flights_finder(params: FlightsInput):
        """Find flights between two airports on given dates. Returns a list of flight offers
        with price, currency, and itinerary/segment details."""
        cache_key = make_cache_key(tool="flights", **params.model_dump())
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info("Flight search cache hit for %s -> %s", params.departure_airport, params.arrival_airport)
            return cached

        slices = [{"origin": params.departure_airport, "destination": params.arrival_airport, "departure_date": params.outbound_date}]
        if params.return_date:
            slices.append({"origin": params.arrival_airport, "destination": params.departure_airport, "departure_date": params.return_date})

        request_body = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"} for _ in range(params.adults)],
                "cabin_class": "economy",
            }
        }
        try:
            raw = client.post("/air/offer_requests", request_body, params={"return_offers": "true"})
            offers = raw.get("data", {}).get("offers", [])[: params.max_results]
            results = [_summarize_offer(offer) for offer in offers]
        except DuffelAPIError as exc:
            logger.warning("Flight search failed: %s", exc)
            return {"error": "Flight search is temporarily unavailable. Please try again shortly."}

        if not results:
            results = {"message": "No flights found for these dates/airports. Try different dates."}

        cache.set(cache_key, results)
        return results

    return flights_finder
