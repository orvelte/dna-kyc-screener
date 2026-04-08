"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def approved_customer():
    """A low-risk customer profile that should not trigger any rules."""
    return {
        "name": "Jane Smith",
        "institution": "University of Edinburgh",
        "country": "GB",
        "customer_type": "academic",
        "end_use": "research",
        "address_type": "institutional",
        "institution_verified": True,
    }


@pytest.fixture
def high_risk_customer():
    """A high-risk customer profile that should trigger multiple rules."""
    return {
        "name": "Unknown Buyer",
        "institution": None,
        "country": "US",
        "customer_type": "individual",
        "end_use": "personal",
        "address_type": "residential",
        "institution_verified": False,
    }
