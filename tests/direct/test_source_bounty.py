import json
from datetime import datetime, timezone, timedelta


CONTRACT = "contracts/source_bounty.py"
REWARD = 2_000_000_000_000_000_000


CHAIN_START = datetime(2035, 1, 1, tzinfo=timezone.utc)


def chain_timestamp(days=7):
    """Use an explicit stored-chain timestamp, never the machine clock."""
    return int((CHAIN_START + timedelta(days=days)).timestamp())


def test_create_claim_and_submit_flow(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.warp("2035-01-01T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = REWARD
    bounty_id = contract.create_bounty(
        "Map the stablecoin landscape",
        "Compare the leading stablecoins and explain their risks for a new builder.",
        "At least five claims, primary links for each, and a short risk comparison.",
        chain_timestamp(),
    )
    assert bounty_id == "bounty-1"
    assert contract.get_bounty(bounty_id)["status"] == "OPEN"

    direct_vm.sender = direct_bob
    direct_vm.value = 0
    contract.claim_bounty(bounty_id)
    assert contract.get_bounty(bounty_id)["status"] == "CLAIMED"

    contract.submit_work(
        bounty_id,
        "A concise report with sourced comparisons and a risk table.",
        json.dumps(["https://example.com/one", "https://example.com/two"]),
    )
    result = contract.get_bounty(bounty_id)
    assert result["status"] == "SUBMITTED"
    from genlayer.py.types import Address
    assert result["claimed_by"] == str(Address(direct_bob))


def test_cannot_claim_own_bounty_or_submit_without_claim(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.warp("2035-01-03T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = REWARD
    bounty_id = contract.create_bounty(
        "A useful research brief",
        "Produce a sourced report with enough detail for a product decision.",
        "Use primary sources and include a clear recommendation.",
        chain_timestamp(),
    )
    with direct_vm.expect_revert("Customer cannot claim"):
        contract.claim_bounty(bounty_id)

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only the claimant"):
        contract.submit_work(bounty_id, "This is not allowed yet.", "[\"https://example.com\"]")


def test_expiry_credits_customer(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.warp("2035-01-01T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = REWARD
    bounty_id = contract.create_bounty(
        "Time-boxed source review",
        "Find and summarize reliable material on a narrow technical topic.",
        "Every material claim must have a public source and a short note.",
        chain_timestamp(1),
    )
    direct_vm.warp("2035-01-03T00:00:00Z")
    contract.expire_bounty(bounty_id)
    assert contract.get_bounty(bounty_id)["status"] == "EXPIRED"
    from genlayer.py.types import Address
    assert contract.get_withdrawable(Address(direct_alice)) == REWARD


def test_submitted_work_cannot_be_expired_for_a_refund(direct_vm, direct_deploy, direct_alice, direct_bob):
    """Delivery must remain reviewable after the delivery deadline."""
    contract = direct_deploy(CONTRACT)
    direct_vm.warp("2035-01-01T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = REWARD
    bounty_id = contract.create_bounty(
        "Reviewable research delivery",
        "Produce a sourced report with enough detail for a product decision.",
        "Use primary sources and include a clear recommendation.",
        chain_timestamp(1),
    )
    direct_vm.sender = direct_bob
    direct_vm.value = 0
    contract.claim_bounty(bounty_id)
    contract.submit_work(
        bounty_id,
        "A complete report with sourced comparisons and a clear recommendation.",
        json.dumps(["https://example.com/one"]),
    )
    direct_vm.warp("2035-01-03T00:00:00Z")
    with direct_vm.expect_revert("already settled"):
        contract.expire_bounty(bounty_id)
    assert contract.get_bounty(bounty_id)["status"] == "SUBMITTED"
    assert contract.get_bounty(bounty_id)["locked_reward"] == str(REWARD)
