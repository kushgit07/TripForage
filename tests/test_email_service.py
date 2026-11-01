from unittest.mock import MagicMock, patch

import pytest

from travel_agent.services import EmailDeliveryError, EmailService


def test_send_html_email_success():
    service = EmailService(api_key="fake-key")
    fake_response = MagicMock(status_code=200, text='{"id": "abc123"}')

    with patch("travel_agent.services.email_service.requests.post") as mock_post:
        mock_post.return_value = fake_response
        service.send_html_email(from_email="a@x.com", to_email="b@x.com", subject="Trip", html_content="<p>hi</p>")

    mock_post.assert_called_once()


def test_send_html_email_raises_on_bad_status():
    service = EmailService(api_key="fake-key")
    fake_response = MagicMock(status_code=400, text='{"message": "bad request"}')

    with patch("travel_agent.services.email_service.requests.post") as mock_post:
        mock_post.return_value = fake_response
        with pytest.raises(EmailDeliveryError):
            service.send_html_email(from_email="a@x.com", to_email="b@x.com", subject="Trip", html_content="<p>hi</p>")


def test_send_html_email_without_api_key_raises_immediately():
    service = EmailService(api_key="")
    with pytest.raises(EmailDeliveryError):
        service.send_html_email(from_email="a@x.com", to_email="b@x.com", subject="Trip", html_content="<p>hi</p>")
