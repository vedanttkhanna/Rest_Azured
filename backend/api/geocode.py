"""Address -> (lat, lng) with Amazon Location Service Places v2 (`geo-places` Geocode)."""
from __future__ import annotations

import os

import boto3

DELHI = [77.2090, 28.6139]  # [lng, lat] bias point
MAX_QUERY = 200  # Geocode QueryText limit; longer text is a ValidationException

_client = None


class GeocodeError(ValueError):
    pass


def _places():
    global _client
    if _client is None:
        _client = boto3.client("geo-places", region_name=os.environ.get("PLACES_REGION") or None)
    return _client


def geocode(address: str) -> dict:
    """Return {"lat", "lng", "label"} for the best match in India, biased towards Delhi."""
    resp = _places().geocode(
        QueryText=address,
        MaxResults=1,
        BiasPosition=DELHI,
        Filter={"IncludeCountries": ["IND"]},
        IntendedUse="Storage",  # we store the coordinates in DynamoDB, which SingleUse results don't allow
    )
    items = resp.get("ResultItems") or []
    if not items or "Position" not in items[0]:
        raise GeocodeError(f"address not found: {address!r}")
    lng, lat = items[0]["Position"]
    label = (items[0].get("Address") or {}).get("Label") or items[0].get("Title") or address
    return {"lat": float(lat), "lng": float(lng), "label": label}
