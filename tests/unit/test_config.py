from __future__ import annotations

import pytest


def test_live_weather_requires_an_operator_contact_user_agent(settings):
    settings.stub_providers = False
    with pytest.raises(ValueError, match="NWS_USER_AGENT"):
        settings.validate_for("weather")

    settings.nws_user_agent = "TravelComparator/1.0 (contact: travel-ops@example.com)"
    settings.validate_for("weather")
