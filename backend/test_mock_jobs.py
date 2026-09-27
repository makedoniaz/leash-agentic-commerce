from mock_jobs import confirm_job, prepare_job, reset_jobs, resolve_transaction


POLICY = {
    "raw_instructions": "Buy one pair of running shoes under CHF 120.",
    "products": {
        "items": [
            {
                "name": "running shoe",
                "category": "sporting_goods",
                "quantity": 1,
                "max_price_per_item": None,
            }
        ]
    },
    "spending": {
        "total_price_max": 120,
        "currency": "CHF",
        "period_in_days": None,
    },
    "merchant": {"blocklist": [], "allowlist": []},
    "order_terms": {
        "require_returnable": True,
        "require_cancellable": True,
    },
    "notes_for_customer": "",
}


def setup_function() -> None:
    reset_jobs()


def test_mock_workflow_produces_all_three_decisions() -> None:
    prepared = prepare_job(0, POLICY)
    assert prepared["status"] == "awaiting_confirmation"
    assert prepared["groups"][0]["results"] == []

    confirmed = confirm_job(prepared["job_id"])
    results = confirmed["groups"][0]["results"]
    assert [result["system_decision"] for result in results] == [
        "approve",
        "decline",
        "step_up",
    ]
    assert confirmed["summary"] == {
        "total": 3,
        "approve": 1,
        "decline": 1,
        "step_up": 1,
        "awaiting_customer": 1,
    }


def test_customer_can_resolve_step_up() -> None:
    prepared = prepare_job(0, POLICY)
    confirmed = confirm_job(prepared["job_id"])
    pending = confirmed["groups"][0]["results"][2]

    resolved = resolve_transaction(
        prepared["job_id"], pending["transaction_id"], "approve"
    )
    assert resolved["status"] == "completed"
    assert resolved["summary"]["approve"] == 2
    assert resolved["summary"]["awaiting_customer"] == 0


def test_generated_payload_contains_no_private_integration_metadata() -> None:
    prepared = prepare_job(0, POLICY)
    payload = str(confirm_job(prepared["job_id"])).casefold()
    assert "api_key" not in payload
    assert "base_url" not in payload
    assert "viseca" not in payload
