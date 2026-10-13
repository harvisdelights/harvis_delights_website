import os
from decimal import Decimal

import requests

SELLER_NAME = "Harvi's Delights"
SELLER_AREA = "Nizampet"
SELLER_PINCODE = "500090"
SERVICEABILITY_URL = "https://apiv2.shiprocket.in/v1/external/courier/serviceability/"
AUTH_URL = "https://apiv2.shiprocket.in/v1/external/auth/login"

def _token():
    token = os.environ.get("SHIPROCKET_API_TOKEN")
    if token:
        return token
    email = os.environ.get("SHIPROCKET_EMAIL")
    password = os.environ.get("SHIPROCKET_PASSWORD")
    if not (email and password):
        return None
    response = requests.post(AUTH_URL, json={"email": email, "password": password}, timeout=10)
    response.raise_for_status()
    return response.json().get("token")

def delivery_estimate(pincode, weight_kg, declared_value):
    """Return a read-only Shiprocket estimate; never creates a shipment."""
    fallback = {"available": False, "source": "standard", "message": "Estimated delivery in 4-7 business days after confirmation.", "courier": ""}
    try:
        token = _token()
        if not token:
            return fallback
        response = requests.get(SERVICEABILITY_URL, headers={"Authorization": f"Bearer {token}"}, params={
            "pickup_postcode": SELLER_PINCODE, "delivery_postcode": pincode, "cod": 0,
            "weight": str(max(Decimal("0.100"), weight_kg)), "declared_value": str(declared_value),
        }, timeout=10)
        response.raise_for_status()
        companies = response.json().get("data", {}).get("available_courier_companies", [])
        if not companies:
            return {"available": False, "source": "shiprocket", "message": "Delivery is not currently available for this pincode.", "courier": ""}
        best = sorted(companies, key=lambda item: float(item.get("estimated_delivery_days") or 999))[0]
        days = best.get("estimated_delivery_days") or "a few"
        etd = best.get("etd")
        return {"available": True, "source": "shiprocket", "message": f"Estimated delivery in {days} business days" + (f" (by {etd})" if etd else ""), "courier": best.get("courier_name", "")}
    except (requests.RequestException, ValueError, TypeError):
        return fallback
