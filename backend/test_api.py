from fastapi.testclient import TestClient
from unittest.mock import patch

import main
from mock_jobs import reset_jobs


client = TestClient(main.app)


def setup_function() -> None:
    reset_jobs()


def test_complete_public_demo_flow() -> None:
    ollama_result = main.DraftWalletPolicy(
        raw_instructions="Buy one pair of running shoes under CHF 120.",
        products={"items": [{
            "name": "running shoes",
            "category": "sporting_goods",
            "quantity": 1,
            "max_price_per_item": None,
        }]},
        spending={"total_price_max": 120, "currency": "CHF", "period_in_days": None},
        merchant={"blocklist": [], "allowlist": []},
        order_terms={"require_returnable": True, "require_cancellable": True},
        notes_for_customer="",
    )
    with patch("main.parse_with_ollama", return_value=ollama_result):
        parsed_response = client.post(
            "/parse-policy",
            json={
                "wallet_id": 0,
                "policy_text": "Buy one pair of running shoes under CHF 120.",
            },
        )
    assert parsed_response.status_code == 200
    parsed = parsed_response.json()
    assert parsed["complete"] is True
    assert parsed["policy"]["products"]["items"][0]["category"] == "sporting_goods"

    prepare_response = client.post(
        "/mock/jobs/prepare",
        json={"wallet_id": 0, "policy": parsed["policy"]},
    )
    assert prepare_response.status_code == 201
    prepared = prepare_response.json()

    confirm_response = client.post(f"/mock/jobs/{prepared['job_id']}/confirm")
    assert confirm_response.status_code == 202
    confirmed = confirm_response.json()
    assert confirmed["status"] == "awaiting_customer"
    assert confirmed["summary"]["total"] == 3

    pending = next(
        result
        for group in confirmed["groups"]
        for result in group["results"]
        if result["system_decision"] == "step_up"
    )
    resolve_response = client.post(
        f"/mock/jobs/{prepared['job_id']}/transactions/{pending['transaction_id']}/resolve",
        json={"decision": "approve"},
    )
    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    assert resolved["status"] == "completed"
    assert resolved["summary"]["awaiting_customer"] == 0


def test_unknown_job_returns_404() -> None:
    response = client.get("/mock/jobs/not-a-job")
    assert response.status_code == 404
