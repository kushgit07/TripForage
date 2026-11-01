import responses

from travel_agent.services import DuffelAPIError, DuffelClient

BASE_URL = "https://api.duffel.com"


@responses.activate
def test_post_sends_bearer_token_and_version_header(duffel_client: DuffelClient):
    responses.add(responses.POST, f"{BASE_URL}/air/offer_requests", json={"data": {"id": "orq_1", "offers": []}}, status=201)

    result = duffel_client.post("/air/offer_requests", {"data": {"slices": []}}, params={"return_offers": "true"})

    assert result == {"data": {"id": "orq_1", "offers": []}}
    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "Bearer test-key"
    assert sent.headers["Duffel-Version"] == "v2"


@responses.activate
def test_get_strips_none_params(duffel_client: DuffelClient):
    responses.add(responses.GET, f"{BASE_URL}/stays/search_results", json={"data": []}, status=200)

    result = duffel_client.get("/stays/search_results", params={"after": None, "limit": 5})

    assert result == {"data": []}
    assert "after" not in responses.calls[0].request.url
    assert "limit=5" in responses.calls[0].request.url


@responses.activate
def test_4xx_raises_duffel_api_error_without_retry(duffel_client: DuffelClient):
    responses.add(responses.POST, f"{BASE_URL}/air/offer_requests", json={"errors": ["bad request"]}, status=400)

    try:
        duffel_client.post("/air/offer_requests", {"data": {}})
        raise AssertionError("expected DuffelAPIError")
    except DuffelAPIError:
        pass

    assert len(responses.calls) == 1  # 4xx errors are not retried


@responses.activate
def test_5xx_raises_duffel_api_error(duffel_client: DuffelClient):
    responses.add(responses.GET, f"{BASE_URL}/air/offers", json={"errors": ["server error"]}, status=500)

    try:
        duffel_client.get("/air/offers")
        raise AssertionError("expected DuffelAPIError")
    except DuffelAPIError:
        pass
