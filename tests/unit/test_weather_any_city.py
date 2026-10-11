import asyncio

from travel_comparator.providers.nws.client import WeatherProvider


def test_stub_weather_supports_cities_outside_the_curated_list():
    provider = WeatherProvider(True, {"cities": []})
    first = asyncio.run(provider.assess("Tokyo"))
    second = asyncio.run(provider.assess("Tokyo"))
    assert first["status"] == "GO"
    assert first["high_celsius"] == second["high_celsius"]
    assert first["illustrative"] is True
