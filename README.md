# SourceBounty

SourceBounty is a GEN-funded research marketplace built as a GenLayer Intelligent Contract.
A customer publishes a brief, rubric, deadline, and reward. A contributor claims it and submits
a report with public evidence URLs. The customer requests review; validators independently fetch
the evidence and judge the report. Consensus then settles the escrow:

- `APPROVE` → the contributor receives withdrawable GEN.
- `REVISE` → the escrow stays locked and the contributor can submit again, for up to three revision rounds.
- `RETRY` → evidence fetching was unavailable; the existing submission and escrow remain pending. The first `RETRY` sets a fixed recovery deadline at the later of the original delivery deadline and three days after that review.
- `REJECT` → the customer receives withdrawable GEN.
- expiry/cancellation → the customer receives a deterministic refund for work that was not submitted.
- A submitted bounty cannot be expired merely because its delivery deadline passes. If evidence
  remains unresolved after the fixed recovery deadline, only the customer can invoke
  `refund_unavailable_bounty`. The claimant may replace evidence before that timestamp; both
  parties may request another review. Replacement or repeated `RETRY` does not extend the window.
  A successful review settles escrow normally. The contract's chain timestamp is authoritative.
- Evidence fetch outages do not immediately trigger a revision or refund. After three
  substantive revision rounds, another revision result becomes a final rejection/refund.
- The wallet reads its caller-specific withdrawable credit through `get_my_withdrawable()`, avoiding
  a fragile frontend conversion from a hex string to the contract's `Address` type.

The frontend is wallet-only and keeps the contract address configurable. The current Studionet
deployment is [`0x6a1E0dca18012655708E6c2DBEc79F968822DCA4`](https://explorer-studio.genlayer.com/address/0x6a1E0dca18012655708E6c2DBEc79F968822DCA4)
(chain ID `61999`), finalized in [transaction `0xe704…4d94`](https://explorer-studio.genlayer.com/tx/0xe70431bc5aa0e4ee9630237c424334bd35ae06c37a25941da6ea87b0dbeb4d94).
The deployed source and this repository's `contracts/source_bounty.py` match after line-ending
normalization and removal of the final newline (SHA-256
`05B6F34B5C71A02A94B24DDFEB170250E88605D7F53B04E62DBDC0144CD8812D`).
Earlier deployments, including `0x43A18CFd4407D37761cDFD5aD11896ee9DE50F16`, remain separate;
their bounty state is not migrated to the new contract.
The two-wallet Studionet QA completed approval/payout, fabricated-report rejection/refund, and
chain-timestamp expiry/refund. See [WALLET-QA-REPORT.md](WALLET-QA-REPORT.md) for exact inputs,
chain times, outcomes, and immutable transaction links. This is test evidence, not a formal audit.

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
