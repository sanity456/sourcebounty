"""Escrow invariants for every SourceBounty settlement path.

Direct mode runs the leader path with mocked evidence and model responses. It
does not substitute for a multi-validator Studionet integration test.
"""

import json
from datetime import datetime, timezone

import pytest

CONTRACT = "contracts/source_bounty.py"
START = "2035-01-01T00:00:00Z"
START_TS = int(datetime(2035, 1, 1, tzinfo=timezone.utc).timestamp())
DAY = 86400
REWARD = 1000
EVIDENCE_URL = "https://example.com/research"
REPORT = "A sufficiently detailed report based on the linked public research source."


def create_bounty(vm, contract, customer, *, deadline_days=7):
    vm.warp(START)
    vm.sender = customer
    vm.value = REWARD
    bounty_id = contract.create_bounty(
        "Research an open technical question",
        "Find credible public information and explain the result for a builder.",
        "Cite a public source and explain how it supports the main claims.",
        START_TS + deadline_days * DAY,
    )
    vm.value = 0
    return bounty_id


def submit(vm, contract, claimant, bounty_id):
    vm.sender = claimant
    contract.claim_bounty(bounty_id)
    contract.submit_work(bounty_id, REPORT, json.dumps([EVIDENCE_URL]))


def mock_review(vm, decision, score, reason):
    vm.clear_mocks()
    vm.mock_web(r"https://example\.com/research", {"status": 200, "body": "Public research evidence."})
    vm.mock_llm(
        r".*reviewing a paid research deliverable.*",
        json.dumps({
            "decision": decision,
            "score": score,
            "reason_code": reason,
            "summary": "Mocked review based on the submitted evidence.",
            "checks": [],
        }),
    )


def credit(contract, account):
    from genlayer.py.types import Address

    return int(contract.get_withdrawable(Address(account)))


def assert_escrow(contract, bounty_id, status, locked, customer, claimant, customer_credit=0, claimant_credit=0):
    bounty = contract.get_bounty(bounty_id)
    assert bounty["status"] == status
    assert int(bounty["locked_reward"]) == locked
    assert credit(contract, customer) == customer_credit
    assert credit(contract, claimant) == claimant_credit


def test_approval_pays_only_claimant_once(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    submit(direct_vm, contract, direct_bob, bounty_id)
    mock_review(direct_vm, "APPROVE", 95, "PASS")

    result = json.loads(contract.evaluate_submission(bounty_id))
    assert result["decision"] == "APPROVE"
    assert_escrow(contract, bounty_id, "REVIEWED", 0, direct_alice, direct_bob, claimant_credit=REWARD)
    with direct_vm.expect_revert("no pending submission"):
        contract.evaluate_submission(bounty_id)
    assert_escrow(contract, bounty_id, "REVIEWED", 0, direct_alice, direct_bob, claimant_credit=REWARD)


def test_reject_refunds_only_customer(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    submit(direct_vm, contract, direct_bob, bounty_id)
    mock_review(direct_vm, "REJECT", 20, "OUT_OF_SCOPE")

    result = json.loads(contract.evaluate_submission(bounty_id))
    assert result["reason_code"] == "OUT_OF_SCOPE"
    assert_escrow(contract, bounty_id, "REVIEWED", 0, direct_alice, direct_bob, customer_credit=REWARD)
    with direct_vm.expect_revert("already settled"):
        contract.expire_bounty(bounty_id)


def test_validator_disagrees_when_independent_review_changes_payout(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    submit(direct_vm, contract, direct_bob, bounty_id)
    mock_review(direct_vm, "APPROVE", 90, "PASS")
    contract.evaluate_submission(bounty_id)

    # Direct mode executes the leader first; run the captured validator with
    # independent web/LLM mocks to check the equivalence rule itself.
    mock_review(direct_vm, "REJECT", 20, "OUT_OF_SCOPE")
    assert direct_vm.run_validator() is False


def test_revision_keeps_escrow_and_grants_real_response_window(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=1)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.warp("2035-01-03T00:00:00Z")
    mock_review(direct_vm, "REVISE", 55, "MISSING_EVIDENCE")

    contract.evaluate_submission(bounty_id)
    bounty = contract.get_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "REVISION", REWARD, direct_alice, direct_bob)
    assert bounty["revision_count"] == "1"
    assert int(bounty["deadline"]) == START_TS + 5 * DAY

    direct_vm.sender = direct_bob
    contract.submit_work(bounty_id, REPORT + " Corrected citations.", json.dumps([EVIDENCE_URL]))
    mock_review(direct_vm, "APPROVE", 82, "PASS")
    direct_vm.sender = direct_alice
    contract.evaluate_submission(bounty_id)
    assert_escrow(contract, bounty_id, "REVIEWED", 0, direct_alice, direct_bob, claimant_credit=REWARD)


def test_evidence_outage_preserves_submission_until_retry(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=1)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.clear_mocks()  # No render mock: the source is unavailable.

    result = json.loads(contract.evaluate_submission(bounty_id))
    assert result["decision"] == "RETRY"
    assert result["reason_code"] == "EVIDENCE_UNAVAILABLE"
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == START_TS + 3 * DAY
    assert_escrow(contract, bounty_id, "SUBMITTED", REWARD, direct_alice, direct_bob)
    assert contract.get_bounty(bounty_id)["revision_count"] == "0"
    with direct_vm.expect_revert("already settled"):
        contract.expire_bounty(bounty_id)

    direct_vm.warp("2035-01-03T00:00:00Z")  # Original delivery deadline has passed.
    direct_vm.sender = direct_bob
    contract.submit_work(bounty_id, REPORT + " Replacement reachable source.", json.dumps([EVIDENCE_URL]))
    assert contract.get_bounty(bounty_id)["review_json"] == ""
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == START_TS + 3 * DAY
    assert_escrow(contract, bounty_id, "SUBMITTED", REWARD, direct_alice, direct_bob)

    mock_review(direct_vm, "APPROVE", 90, "PASS")
    # Claimant may trigger review if customer is absent.
    contract.evaluate_submission(bounty_id)
    assert_escrow(contract, bounty_id, "REVIEWED", 0, direct_alice, direct_bob, claimant_credit=REWARD)
    assert contract.get_bounty(bounty_id)["retry_deadline"] == "0"


def test_retry_deadline_is_fixed_and_only_customer_can_refund_at_boundary(
    direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie
):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=1)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.clear_mocks()
    contract.evaluate_submission(bounty_id)
    deadline = START_TS + 3 * DAY
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == deadline

    direct_vm.warp("2035-01-02T00:00:00Z")
    contract.evaluate_submission(bounty_id)
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == deadline
    direct_vm.sender = direct_bob
    contract.submit_work(bounty_id, REPORT + " Replacement source.", json.dumps([EVIDENCE_URL]))
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == deadline
    contract.evaluate_submission(bounty_id)
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == deadline

    direct_vm.sender = direct_alice
    direct_vm.warp("2035-01-03T23:59:59Z")
    with direct_vm.expect_revert("has not passed"):
        contract.refund_unavailable_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "SUBMITTED", REWARD, direct_alice, direct_bob)

    direct_vm.warp("2035-01-04T00:00:00Z")
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only the customer"):
        contract.refund_unavailable_bounty(bounty_id)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("replacement window has passed"):
        contract.submit_work(bounty_id, REPORT + " Too late.", json.dumps([EVIDENCE_URL]))
    direct_vm.sender = direct_alice
    contract.refund_unavailable_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "EXPIRED", 0, direct_alice, direct_bob, customer_credit=REWARD)
    with direct_vm.expect_revert("no unresolved evidence outage"):
        contract.refund_unavailable_bounty(bounty_id)


def test_replacement_pending_after_retry_deadline_can_be_refunded(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=1)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.clear_mocks()
    contract.evaluate_submission(bounty_id)
    direct_vm.sender = direct_bob
    contract.submit_work(bounty_id, REPORT + " Replacement source.", json.dumps([EVIDENCE_URL]))
    direct_vm.warp("2035-01-04T00:00:00Z")
    direct_vm.sender = direct_alice
    contract.refund_unavailable_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "EXPIRED", 0, direct_alice, direct_bob, customer_credit=REWARD)


def test_early_retry_never_shortens_original_delivery_deadline(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=7)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.clear_mocks()
    contract.evaluate_submission(bounty_id)
    assert int(contract.get_bounty(bounty_id)["retry_deadline"]) == START_TS + 7 * DAY
    direct_vm.warp("2035-01-04T00:00:00Z")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("has not passed"):
        contract.refund_unavailable_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "SUBMITTED", REWARD, direct_alice, direct_bob)


def test_fourth_revision_becomes_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    submit(direct_vm, contract, direct_bob, bounty_id)
    mock_review(direct_vm, "REVISE", 55, "LOW_QUALITY")

    for round_number in range(1, 5):
        direct_vm.sender = direct_alice
        result = json.loads(contract.evaluate_submission(bounty_id))
        bounty = contract.get_bounty(bounty_id)
        if round_number < 4:
            assert result["decision"] == "REVISE"
            assert_escrow(contract, bounty_id, "REVISION", REWARD, direct_alice, direct_bob)
            assert bounty["revision_count"] == str(round_number)
            direct_vm.sender = direct_bob
            contract.submit_work(bounty_id, REPORT + f" Revision {round_number}.", json.dumps([EVIDENCE_URL]))
        else:
            assert result["decision"] == "REJECT"
            assert result["reason_code"] == "LOW_QUALITY"
            assert_escrow(contract, bounty_id, "REVIEWED", 0, direct_alice, direct_bob, customer_credit=REWARD)
            assert bounty["revision_count"] == "3"


def test_cancellation_refunds_only_open_bounty(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only the customer"):
        contract.cancel_bounty(bounty_id)
    direct_vm.sender = direct_alice
    contract.cancel_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "CANCELED", 0, direct_alice, direct_bob, customer_credit=REWARD)
    with direct_vm.expect_revert("Only open"):
        contract.cancel_bounty(bounty_id)

    second_id = create_bounty(direct_vm, contract, direct_alice)
    direct_vm.sender = direct_bob
    contract.claim_bounty(second_id)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Only open"):
        contract.cancel_bounty(second_id)
    assert int(contract.get_bounty(second_id)["locked_reward"]) == REWARD


def test_claimed_expiry_refunds_customer_only_after_chain_deadline(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=1)
    direct_vm.sender = direct_bob
    contract.claim_bounty(bounty_id)
    with direct_vm.expect_revert("has not passed"):
        contract.expire_bounty(bounty_id)
    direct_vm.warp("2035-01-02T00:00:00Z")
    contract.expire_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "EXPIRED", 0, direct_alice, direct_bob, customer_credit=REWARD)
    with direct_vm.expect_revert("already settled"):
        contract.expire_bounty(bounty_id)


def test_unanswered_revision_expires_to_customer(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice, deadline_days=1)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.warp("2035-01-03T00:00:00Z")
    mock_review(direct_vm, "REVISE", 50, "MISSING_EVIDENCE")
    contract.evaluate_submission(bounty_id)
    assert_escrow(contract, bounty_id, "REVISION", REWARD, direct_alice, direct_bob)
    with direct_vm.expect_revert("has not passed"):
        contract.expire_bounty(bounty_id)
    direct_vm.warp("2035-01-06T00:00:00Z")
    contract.expire_bounty(bounty_id)
    assert_escrow(contract, bounty_id, "EXPIRED", 0, direct_alice, direct_bob, customer_credit=REWARD)


def test_unauthorized_review_cannot_change_escrow(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    submit(direct_vm, contract, direct_bob, bounty_id)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only the customer or claimant"):
        contract.evaluate_submission(bounty_id)
    assert_escrow(contract, bounty_id, "SUBMITTED", REWARD, direct_alice, direct_bob)


def test_empty_withdrawal_reverts_without_credit_change(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("No withdrawable GEN"):
        contract.withdraw()
    assert credit(contract, direct_alice) == 0


@pytest.mark.parametrize("unsafe_url", [
    "http://example.com/research",
    "https://localhost/research",
    "https://127.0.0.1/research",
    "https://169.254.169.254/latest/meta-data",
    "https://internal.local/report",
    "https://user@example.com/report",
    "https://example.com:8443/report",
    "https://example.com/space here",
])
def test_unsafe_evidence_url_cannot_lock_submitted_work(direct_vm, direct_deploy, direct_alice, direct_bob, unsafe_url):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    direct_vm.sender = direct_bob
    contract.claim_bounty(bounty_id)
    with direct_vm.expect_revert("Evidence"):
        contract.submit_work(bounty_id, REPORT, json.dumps([unsafe_url]))
    assert_escrow(contract, bounty_id, "CLAIMED", REWARD, direct_alice, direct_bob)


def test_refund_withdrawal_clears_credit_once(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    bounty_id = create_bounty(direct_vm, contract, direct_alice)
    contract.cancel_bounty(bounty_id)
    assert credit(contract, direct_alice) == REWARD
    assert int(contract.withdraw()) == REWARD
    assert credit(contract, direct_alice) == 0
    with direct_vm.expect_revert("No withdrawable GEN"):
        contract.withdraw()
