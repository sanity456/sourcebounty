# SourceBounty

SourceBounty is a GEN-funded research marketplace built as a GenLayer Intelligent Contract.
A customer publishes a brief, rubric, deadline, and reward. A contributor claims it and submits
a report with public evidence URLs. The customer requests review; validators independently fetch
the evidence and judge the report. Consensus then settles the escrow:

- `APPROVE` → the contributor receives withdrawable GEN.
- `REVISE` → the escrow stays locked and the contributor can submit again, for up to three revision rounds.
- `RETRY` → evidence fetching was unavailable; the existing submission and escrow remain pending without extending the deadline or incrementing revisions.
- `REJECT` → the customer receives withdrawable GEN.
- expiry/cancellation → the customer receives a deterministic refund for work that was not submitted.
- submitted work is never expired; the customer or claimant can request the consensus review so a
  customer cannot receive a delivery and reclaim its escrow by staying silent.
- Evidence fetch outages do not trigger a revision, refund, or deadline extension. After three
  substantive revision rounds, another revision result becomes a final rejection/refund.
- The wallet reads its caller-specific withdrawable credit through `get_my_withdrawable()`, avoiding
  a fragile frontend conversion from a hex string to the contract's `Address` type.

The frontend is wallet-only and keeps the contract address configurable. The current Studionet
test deployment is `0x43A18CFd4407D37761cDFD5aD11896ee9DE50F16` (chain ID `61999`).
Earlier deployments predate the settlement fairness fix and must not be substituted for it.
The local two-wallet test completed create → claim → submit → consensus approval → withdraw,
including a final zero withdrawable-credit reading. This is test evidence, not a formal audit.

## Project layout

```text
sourcebounty/
├─ contracts/source_bounty.py       # Intelligent Contract / escrow authority
├─ frontend/                        # Vite wallet UI
│  ├─ src/main.js                   # GenLayerJS reads, writes, and actions
│  └─ src/styles.css                # responsive SourceBounty UI
└─ tests/direct/                    # deterministic state-transition tests
```

## Contract boundary

The contract owns the minimum authoritative state: bounty terms, escrow balance, claimant,
submission, evidence URLs, review result, status transitions, and withdrawable credit. The
frontend owns presentation, wallet connection, filtering, and convenience prompts. Validators
own the independent evidence fetch and review; no frontend score is trusted for settlement.

## Local checks

From the workspace root:

```powershell
$lint = 'C:\Users\user\.codex\runtimes\genlayer-new12-20260821\Scripts\genvm-lint.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:GENVM_VERSION = 'v0.2.16'
& $lint check sourcebounty\contracts\source_bounty.py
```

The contract must retain the pinned `Depends` runner on line 1. Do not replace it with `test`,
`latest`, or an unversioned runner alias.

The frontend can be built with:

```powershell
cd sourcebounty\frontend
npm install
npm run build
```

On the current Windows/OneDrive checkout, npm's executable shim can be unavailable. The equivalent
verification command is `node node_modules/vite/bin/vite.js build`.

Run the complete direct suite with `python -m pytest tests/direct -q`. The tests cover all four
review outcomes, the three-round revision limit, cancellation, expiry, access control, duplicate
settlement, and withdrawal credit accounting. Direct mode runs the leader path with mocked
web/LLM responses; it does not exercise real multi-validator consensus or final delivery of an
external GEN transfer. `tests/direct/conftest.py` uses a pipe-based stdin shim so the tests run on
Windows despite the upstream temporary-file locking issue.

## Deploy to Studionet

Use the matching GenLayer CLI and the stable Studionet profile (chain ID `61999`). From this
directory, after configuring an account with enough GEN for deployment and fees:

```bash
genlayer network set studionet
genlayer deploy --contract contracts/source_bounty.py
```

The currently tested Studionet contract address is shown above. For a new deployment, record its
immutable deployment transaction, verify its source against this repository, set the new address
through **Contract settings**, and repeat the two-wallet flow. Do not use a production wallet or
meaningful funds until the full test matrix and an independent review pass.

## Security notes

- Reward value is accepted only by `create_bounty` and is never released directly by the UI.
- A customer cannot claim its own bounty; only the claimant can submit; the customer or claimant
  can request review.
- Reviews compare decision and score band across independent runs, rather than trusting one model
  output or checking JSON shape only.
- User text and fetched pages are marked as untrusted data in the review prompt to reduce prompt
  injection risk.
- Payouts are credited first and transferred only through a finalized external message.
- Time checks use GenLayer's deterministic transaction timestamp, not a validator's host clock.

This is an MVP foundation, not a formal audit. Before a public launch, add integration tests on the
target network, an appeal policy, rate limits/indexing, and an independent security review.
