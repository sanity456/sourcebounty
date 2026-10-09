# SourceBounty Studionet wallet QA

- Test date: 2026-10-09
- Network: GenLayer Studionet, chain ID `61999`
- Contract: [`0x6a1E0dca18012655708E6c2DBEc79F968822DCA4`](https://explorer-studio.genlayer.com/address/0x6a1E0dca18012655708E6c2DBEc79F968822DCA4)
- Repository revision tested: [`2f0108c091d4a9afd6dff67db131330d74d8f75e`](https://github.com/sanity456/sourcebounty/commit/2f0108c091d4a9afd6dff67db131330d74d8f75e)

This was a two-wallet end-to-end QA run against the deployed Studionet contract. Wallet A was the customer (address suffix `97D0`); wallet B was the contributor (suffix `9360`). Each transaction receipt listed below returned status `0x1`. Transaction fees are separate from the stated contract value.

## Test cases and results

### 1. Evidence-supported approval and contributor payout

- **Bounty:** `bounty-1`, “Studionet QA: Example Domain verification”
- **Reward:** 1,000 wei; final locked reward: 0 wei
- **Brief:** Explain what the Example Domain page is for. Use only the public text at `https://example.com/` and avoid unsupported claims.
- **Rubric:** Approve an accurate description of Example Domain as illustrative documentation examples, with the source cited and no invented claims.
- **Submitted report:** “According to the Example Domain page, this domain is for illustrative examples in documentation and can be used without permission. Source: https://example.com/.”
- **Evidence:** `https://example.com/`
- **Consensus result:** `APPROVE`, reason `PASS`, score `95`; bounty state `REVIEWED`.
- **Settlement:** 1,000 wei became contributor B's withdrawable credit; withdrawal completed and the contract-to-B transfer finalized.

[Review transaction](https://explorer-studio.genlayer.com/tx/0xc99c23edefdda6982bc0bd8441ee61fa035254d671315092f160709387f0e4cb) · [Withdrawal transaction](https://explorer-studio.genlayer.com/tx/0x09d09bc7fb4f791bb02d580f791e19f08b774a60db6efd942b75d541b255b0d2) · [Finalized transfer](https://explorer-studio.genlayer.com/tx/0x8a1b15fdb67f728ccd24ea13675039c5fe28b89703db4cc57d27a3db410e87bf)

### 2. Fabricated report rejection and customer refund

- **Bounty:** `bounty-3`, “QA fabricated-report rejection 6103e13d”
- **Reward:** 1,000 wei; final locked reward: 0 wei
- **Brief:** Explain what `https://example.com/` is for, using only that page and citing it.
- **Rubric:** Approve a factual description of the page as documentation examples; reject fabricated commercial claims as materially unusable.
- **Submitted report:** “Example Domain is a live travel-booking company that sells airline tickets, rents hotel rooms, and operates a customer-support hotline. These are the findings of this research report, supposedly documented at https://example.com/.”
- **Evidence:** `https://example.com/`
- **Consensus result:** `REJECT`, reason `UNVERIFIABLE`, score `2`; validators noted that the cited page is reserved for illustrative documentation examples and is not a service.
- **Settlement:** 1,000 wei became customer A's withdrawable credit; the withdrawal and contract-to-A refund transfer finalized.

[Create transaction](https://explorer-studio.genlayer.com/tx/0x4a6c07b870d4d0e045a1e01ba04047296fea8b151a2ba066b7e4365785ebc21d) · [Claim transaction](https://explorer-studio.genlayer.com/tx/0xe96d3cbb5d0c239ea9f34708ca40519dfc53ee5d54bd2f7ecbab8d3c6e553bc6) · [Submission transaction](https://explorer-studio.genlayer.com/tx/0xfcdb7f65f8149948ebd47d33f8b239502eaac8878ad8db46c966c1708f744c28) · [Review transaction](https://explorer-studio.genlayer.com/tx/0x72fa6c92281ffa3e7a4db02e5dae5491bf0658535a20cca03545d64a5ddebe09) · [Withdrawal transaction](https://explorer-studio.genlayer.com/tx/0xa8b268d0c5764c7b437a58f1fe605980de37a82138994dd488392f9fe8369319) · [Finalized refund transfer](https://explorer-studio.genlayer.com/tx/0xa59d0783da4ed1a9cd0e8e97993d4f36ae12af1c254b00ed21508f23fd8527e2)

### 3. Unclaimed-bounty expiry using stored chain time

- **Bounty:** `bounty-2`, “QA unclaimed expiry 6103e13d”
- **Reward:** 1,000 wei; no claimant and no submission
- **Brief:** “QA only: an unclaimed brief to test expiry against a stored chain timestamp. Do not claim or submit work.”
- **Rubric:** “No work is expected. The customer should recover escrow only when the contract's deadline has passed.”
- **Stored deadline:** Unix timestamp `1791547302` = `2026-10-09T12:01:42Z` = `2026-10-09 13:01:42` Nigeria time (WAT).
- **Before-deadline check:** chain timestamp `1791545353`; state `OPEN`; `eligible_to_expire: false`.
- **After-deadline check:** chain timestamp `1791547361`; state was eligible to expire. A later read returned state `EXPIRED`, locked reward `0` wei, at chain timestamp `1791547781`.
- **Refund:** A's withdrawable credit read `1000` wei before withdrawal and `0` afterward. Withdrawal receipt succeeded.
- **Receipt note:** The expiry action's transaction hash was not retained in this report. The transition is evidenced by the before/after contract reads and the linked successful withdrawal; the withdrawal transaction itself is linked below.

[Bounty creation transaction](https://explorer-studio.genlayer.com/tx/0xb66e535dfa43f907c032b18fbf8346be129bd2c798e8c4ab2e148af306529a00) · [Refund withdrawal transaction](https://explorer-studio.genlayer.com/tx/0xd577b2e9d0bbc8717532fb699315eb9f1d2e2b7e81f05747aabfd7d6bf1df61c)

## Reproducible checks

- Complete direct-mode contract suite: **27 passed**.
- GenVM lint: **passed**, 3 checks; the contract declares the pinned GenVM runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`.
- Frontend JavaScript syntax checks: **passed**.
- Production Vite build: **passed**. It emits a non-blocking warning because the main JavaScript chunk is 543.26 kB before gzip (119.09 kB gzipped).
- `npm audit`: **0 vulnerabilities**.
- Public GitHub Actions at the tested revision: [run 37806963535 succeeded](https://github.com/sanity456/sourcebounty/actions/runs/37806963535).
- Public demo returned HTTP 200: [sourcebounty.vercel.app](https://sourcebounty.vercel.app).
- The public GitHub repository is accessible without signing in: [sanity456/sourcebounty](https://github.com/sanity456/sourcebounty).
- `genlayer code` retrieved the deployed source; byte-for-byte text comparison matched the repository after line-ending normalization and removal of its final newline. SHA-256: `05B6F34B5C71A02A94B24DDFEB170250E88605D7F53B04E62DBDC0144CD8812D`.

## Scope and limitations

This verifies the listed wallet flows on Studionet and the deterministic contract suite; it is not an independent security audit or a production-mainnet certification. The expiry action hash was not retained, and this QA used the public Example Domain page as its evidence fixture. The Vite bundle-size warning is a performance follow-up, not a failed build.
