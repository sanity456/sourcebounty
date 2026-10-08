import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";
import "./styles.css";

const ZERO = "0x0000000000000000000000000000000000000000";
const LEGACY_CONTRACT = "0x47bbc16ACbAFb18CBd8a896fb147AEA71DD95134";
const CURRENT_CONTRACT = "0x43A18CFd4407D37761cDFD5aD11896ee9DE50F16";
const configuredContract = localStorage.getItem("sourcebounty.contract") || "";
// Never silently point a fixed frontend at the pre-fix deployment.
const DEFAULT_CONTRACT = configuredContract && configuredContract.toLowerCase() !== LEGACY_CONTRACT.toLowerCase() ? configuredContract : CURRENT_CONTRACT;
const ABI = [
  { type: "function", name: "list_bounties", stateMutability: "view", inputs: [], outputs: [{ type: "string" }] },
  { type: "function", name: "get_bounty", stateMutability: "view", inputs: [{ name: "bounty_id", type: "string" }], outputs: [{ type: "string" }] },
  { type: "function", name: "get_my_withdrawable", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "create_bounty", stateMutability: "payable", inputs: [{ name: "title", type: "string" }, { name: "brief", type: "string" }, { name: "rubric", type: "string" }, { name: "deadline", type: "uint256" }], outputs: [{ type: "string" }] },
  { type: "function", name: "claim_bounty", stateMutability: "nonpayable", inputs: [{ name: "bounty_id", type: "string" }], outputs: [] },
  { type: "function", name: "submit_work", stateMutability: "nonpayable", inputs: [{ name: "bounty_id", type: "string" }, { name: "report", type: "string" }, { name: "evidence_json", type: "string" }], outputs: [] },
  { type: "function", name: "evaluate_submission", stateMutability: "nonpayable", inputs: [{ name: "bounty_id", type: "string" }], outputs: [{ type: "string" }] },
  { type: "function", name: "cancel_bounty", stateMutability: "nonpayable", inputs: [{ name: "bounty_id", type: "string" }], outputs: [] },
  { type: "function", name: "expire_bounty", stateMutability: "nonpayable", inputs: [{ name: "bounty_id", type: "string" }], outputs: [] },
  { type: "function", name: "withdraw", stateMutability: "nonpayable", inputs: [], outputs: [{ type: "uint256" }] },
];

const state = {
  account: "",
  contract: DEFAULT_CONTRACT,
  bounties: [],
  selected: null,
  filter: "all",
  loading: false,
  message: "",
  error: "",
  client: null,
  provider: null,
  withdrawable: "0",
  pending: false,
  submitOpen: false,
  formDrafts: {},
};

function short(address) {
  return address ? `${address.slice(0, 6)}…${address.slice(-4)}` : "Not connected";
}

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
}

function toGen(wei) {
  const n = BigInt(wei || 0);
  const whole = n / 10n ** 18n;
  // Show the exact escrow amount; tiny Studionet rewards must not appear as 0 GEN.
  const fraction = (n % 10n ** 18n).toString().padStart(18, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : `${whole}`;
}

function toWei(gen) {
  const value = String(gen).trim();
  if (!/^\d+(\.\d{1,18})?$/.test(value)) throw new Error("Reward must be a decimal GEN amount with up to 18 decimals.");
  const [whole, fraction = ""] = value.split(".");
  return (BigInt(whole || "0") * 10n ** 18n + BigInt((fraction + "0".repeat(18)).slice(0, 18))).toString();
}

function nowPlusDays(days) {
  return Math.floor(Date.now() / 1000) + Number(days) * 86400;
}

function clientFor(account = undefined) {
  if (!state.contract) return null;
  const options = { chain: studionet };
  if (account) options.account = account;
  if (state.provider) options.provider = state.provider;
  state.client = createClient(options);
  return state.client;
}

async function metaMaskProvider() {
  if (state.provider) return state.provider;
  // EIP-6963 identifies the extension without relying on injection order.
  const announced = [];
  const onAnnounce = (event) => announced.push(event.detail);
  window.addEventListener("eip6963:announceProvider", onAnnounce);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  await new Promise((resolve) => setTimeout(resolve, 400));
  window.removeEventListener("eip6963:announceProvider", onAnnounce);
  const found = announced.find(({ info }) => info?.rdns === "io.metamask")?.provider
    || (window.ethereum?.providers || []).find((provider) => provider.isMetaMask && !provider.isPhantom)
    || (window.ethereum?.isMetaMask && !window.ethereum?.isPhantom ? window.ethereum : null);
  if (!found) throw new Error("MetaMask was not detected. Enable its extension for this site and try again.");
  state.provider = found;
  found.on?.("accountsChanged", (accounts) => { state.account = accounts[0] || ""; state.withdrawable = "0"; render(); refresh(); });
  found.on?.("chainChanged", () => { state.error = "Network changed. Reconnect to GenLayer Studionet."; state.account = ""; render(); });
  return found;
}

function setToast() {
  const toast = document.querySelector("#toast");
  if (!toast) return;
  toast.textContent = state.error || state.message || "";
  toast.classList.toggle("show", Boolean(state.error || state.message));
}

async function connect() {
  const provider = await metaMaskProvider();
  const accounts = await provider.request({ method: "eth_requestAccounts" });
  const chain = await provider.request({ method: "eth_chainId" });
  if (Number.parseInt(chain, 16) !== 61999) {
    const chainId = `0x${studionet.id.toString(16)}`;
    try {
      await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId }] });
    } catch (error) {
      if (error?.code !== 4902) throw error;
      await provider.request({ method: "wallet_addEthereumChain", params: [{ chainId, chainName: studionet.name, rpcUrls: studionet.rpcUrls.default.http, nativeCurrency: studionet.nativeCurrency, blockExplorerUrls: [studionet.blockExplorers.default.url] }] });
      await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId }] });
    }
  }
  state.account = accounts[0] || "";
  render();
  await refresh();
}

async function read(name, args = []) {
  if (!state.contract) return null;
  const client = clientFor(state.account || undefined);
  return client.readContract({ address: state.contract, abi: ABI, functionName: name, args });
}

async function write(name, args = [], value) {
  if (!state.account) await connect();
  if (!state.contract) throw new Error("Add the deployed SourceBounty contract address in Settings first.");
  if (state.pending) throw new Error("A wallet transaction is already in progress.");
  const client = clientFor(state.account);
  // GenLayerJS packages the consensus call for the connected browser wallet.
  // The bounty reward is the intentional contract value, separate from fees.
  state.pending = true;
  state.message = `Waiting for MetaMask to confirm ${name}…`;
  state.error = "";
  setToast();
  try {
    const hash = await client.writeContract({ address: state.contract, functionName: name, args, value: BigInt(value || 0) });
    state.message = `${name} sent (${short(hash)}). Waiting for final consensus…`;
    setToast();
    let receipt;
    try {
      // Studionet consensus can take longer than the SDK's 30-second default.
      receipt = await client.waitForTransactionReceipt({ hash, status: "FINALIZED", interval: 5000, retries: 120 });
    } catch (error) {
      if (/Timed out waiting for transaction/i.test(String(error?.message || ""))) {
        throw new Error(`${name} was sent (${hash}) but is still awaiting finality. Check the transaction before retrying.`);
      }
      throw error;
    }
    const status = String(receipt.statusName ?? receipt.status_name ?? "").toUpperCase();
    const execution = String(receipt.txExecutionResultName ?? receipt.tx_execution_result_name ?? "").toUpperCase();
    const result = String(receipt.resultName ?? receipt.result_name ?? "").toUpperCase();
    const failedOutcome = receiptHasFailedOutcome(receipt);
    if (status !== "FINALIZED" || failedOutcome) throw new Error(`${name} did not finalize successfully (${execution || result || status || "unknown result"}).`);
    state.message = `${name} finalized successfully.`;
    return receipt;
  } finally {
    state.pending = false;
    setToast();
  }
}

function receiptHasFailedOutcome(value) {
  if (!value || typeof value !== "object") return false;
  for (const [key, entry] of Object.entries(value)) {
    const field = key.toLowerCase();
    if (typeof entry === "string" && (field.includes("execution") || field.includes("result") || field.includes("status"))) {
      const outcome = entry.toUpperCase();
      if (["FAILURE", "FAILED", "REVERTED", "FINISHED_WITH_ERROR", "EXECUTION_ERROR"].includes(outcome)) return true;
    } else if (entry && typeof entry === "object" && receiptHasFailedOutcome(entry)) return true;
  }
  return false;
}

async function refresh() {
  if (!state.contract) { render(); return; }
  state.loading = true; state.error = ""; render();
  try {
    const raw = await read("list_bounties");
    state.bounties = Array.isArray(raw) ? raw : (typeof raw === "string" ? JSON.parse(raw) : []);
    if (state.selected) {
      const fresh = await read("get_bounty", [state.selected.bounty_id]);
      state.selected = typeof fresh === "string" ? JSON.parse(fresh) : fresh;
    }
    if (state.account) {
      const credit = await read("get_my_withdrawable");
      state.withdrawable = String(credit ?? "0");
    }
  } catch (error) { state.error = error.message || String(error); }
  state.loading = false; render();
}

function statusLabel(status) {
  return { OPEN: "Open", CLAIMED: "Claimed", SUBMITTED: "Review queue", REVISION: "Revision requested", REVIEWED: "Settled", EXPIRED: "Expired", CANCELED: "Canceled" }[status] || status;
}

function captureFormDrafts() {
  for (const form of document.querySelectorAll("form[id]")) {
    const draft = {};
    for (const field of form.querySelectorAll("[name]")) {
      draft[field.name] = { value: field.value, checked: "checked" in field ? field.checked : undefined };
    }
    state.formDrafts[form.id] = draft;
  }
}

function restoreFormDrafts() {
  for (const form of document.querySelectorAll("form[id]")) {
    const draft = state.formDrafts[form.id];
    if (!draft) continue;
    for (const field of form.querySelectorAll("[name]")) {
      const saved = draft[field.name];
      if (!saved) continue;
      field.value = saved.value;
      if (saved.checked !== undefined) field.checked = saved.checked;
    }
  }
}

function clearFormDraft(id) { delete state.formDrafts[id]; }

function bountyCard(bounty) {
  const active = state.selected?.bounty_id === bounty.bounty_id;
  return `<button class="bounty-card ${active ? "active" : ""}" data-bounty="${esc(bounty.bounty_id)}">
    <div class="card-top"><span class="eyebrow">${esc(bounty.bounty_id)}</span><span class="status status-${esc(bounty.status)}">${statusLabel(bounty.status)}</span></div>
    <h3>${esc(bounty.title)}</h3>
    <div class="card-meta"><span class="reward">${toGen(bounty.reward)} GEN</span><span>${new Date(Number(bounty.deadline) * 1000).toLocaleDateString()}</span></div>
  </button>`;
}

function detailPanel() {
  const b = state.selected;
  if (!b) return `<div class="empty-detail"><div class="orbit-mark">◎</div><h2>Pick a bounty</h2><p>Open a brief to see the evidence standard, claim the work, or review a submission.</p></div>`;
  const isCustomer = state.account && b.customer?.toLowerCase() === state.account.toLowerCase();
  const isClaimant = state.account && b.claimed_by?.toLowerCase() === state.account.toLowerCase();
  let actions = "";
  if (b.status === "OPEN" && !isCustomer) actions += `<button class="primary action" data-action="claim">Claim this brief <span>↗</span></button>`;
  if ((b.status === "CLAIMED" || b.status === "REVISION") && isClaimant) actions += `<button class="primary action" data-action="submit">Submit research <span>↗</span></button>`;
  if (b.status === "SUBMITTED" && (isCustomer || isClaimant)) actions += `<button class="primary action" data-action="evaluate">Run consensus review <span>↗</span></button>`;
  if (b.status === "OPEN" && isCustomer) actions += `<button class="quiet action" data-action="cancel">Cancel & refund</button>`;
  if (["OPEN", "CLAIMED", "REVISION"].includes(b.status)) actions += `<button class="quiet action" data-action="expire">Check expiry</button>`;
  const evidence = (() => { try { return JSON.parse(b.evidence_json || "[]"); } catch { return []; } })();
  let review = "";
  if (b.review_json) { try { const r = JSON.parse(b.review_json); const retry = r.decision === "RETRY"; review = `<div class="review ${retry ? "review-retry" : ""}"><div class="card-top"><span class="eyebrow">${retry ? "Review paused · retry available" : "Consensus result"}</span>${retry ? "" : `<strong>${esc(r.score)}/100</strong>`}</div><p>${esc(r.summary)}</p><span class="reason">${esc(r.reason_code)}</span></div>`; } catch { review = ""; } }
  return `<article class="detail-card">
    <div class="detail-kicker"><span class="status status-${esc(b.status)}">${statusLabel(b.status)}</span><span>${toGen(b.reward)} GEN escrow</span></div>
    <h2>${esc(b.title)}</h2><p class="detail-brief">${esc(b.brief)}</p>
    <div class="rule"><span>Success rubric</span><p>${esc(b.rubric)}</p></div>
    ${b.report ? `<div class="rule"><span>Latest submission</span><p class="report-preview">${esc(b.report)}</p><div class="evidence-list">${evidence.map((u) => `<a href="${esc(u)}" target="_blank" rel="noreferrer">${esc(u)}</a>`).join("")}</div></div>` : ""}
    ${review}
    ${state.submitOpen && isClaimant ? `<form id="submit-form" class="submit-form"><label>Report<textarea name="report" minlength="40" maxlength="12000" required placeholder="Paste the completed research report"></textarea></label><label>Evidence URLs<textarea name="evidence" required placeholder="One https:// URL per line"></textarea></label><div class="form-row"><button class="primary" type="submit">Submit for review ↗</button><button class="quiet" type="button" data-action="close-submit">Cancel</button></div></form>` : ""}
    <div class="detail-footer"><span>Deadline ${new Date(Number(b.deadline) * 1000).toLocaleString()}</span><div class="actions">${actions}</div></div>
  </article>`;
}

function appTemplate() {
  const hasContract = Boolean(state.contract);
  const visible = state.bounties.filter((b) => state.filter === "all" || b.status === state.filter);
  return `<div class="shell">
    <header class="topbar"><a class="brand" href="#"><span class="brand-mark">✳</span><span>source<span>bounty</span></span></a><div class="network"><i></i> GenLayer Studionet</div><div class="wallet-tools">${state.account ? `<span class="credit">Credit ${toGen(state.withdrawable)} GEN</span><button class="quiet" id="withdraw" ${state.pending || state.withdrawable === "0" ? "disabled" : ""}>Withdraw</button>` : ""}<button class="wallet ${state.account ? "connected" : ""}" id="connect">${state.account ? short(state.account) : "Connect wallet"}</button></div></header>
    <main>
      <section class="hero"><div><p class="eyebrow lime">RESEARCH, WITH RECEIPTS</p><h1>Fund the question.<br/><em>Reward the evidence.</em></h1><p class="hero-copy">SourceBounty turns a clear brief into a live GEN escrow. Contributors deliver research, validators inspect the sources, and consensus decides where the reward goes.</p><div class="hero-actions"><a class="primary" href="#create">Post a bounty <span>↘</span></a><button class="text-button" id="scroll-bounties">Browse open work <span>↓</span></button></div></div><div class="hero-art"><div class="art-ring ring-a"></div><div class="art-ring ring-b"></div><div class="art-core">SB<span>✦</span></div><div class="art-note note-a">evidence<br/><b>verified</b></div><div class="art-note note-b">GEN<br/><b>escrow</b></div></div></section>
      <section class="stats"><div><span class="stat-value">${hasContract ? state.bounties.length : "—"}</span><span>briefs published</span></div><div><span class="stat-value">${hasContract ? state.bounties.filter((b) => b.status === "OPEN").length : "—"}</span><span>open to claim</span></div><div><span class="stat-value">${hasContract ? state.bounties.filter((b) => ["REVIEWED", "EXPIRED", "CANCELED"].includes(b.status)).length : "—"}</span><span>settled on-chain</span></div><div class="stats-note">No email. No platform custody.<br/><b>Wallet → work → consensus.</b></div></section>
      <section class="workspace" id="bounties"><div class="section-head"><div><p class="eyebrow">THE MARKET</p><h2>Open briefs</h2></div><div class="filters"><button class="filter ${state.filter === "all" ? "selected" : ""}" data-filter="all">All</button><button class="filter ${state.filter === "OPEN" ? "selected" : ""}" data-filter="OPEN">Open</button><button class="filter ${state.filter === "SUBMITTED" ? "selected" : ""}" data-filter="SUBMITTED">In review</button></div></div><div class="market-grid"><div class="bounty-list">${state.loading ? `<div class="loading">Reading the contract…</div>` : !hasContract ? `<div class="loading">Set the updated contract address in settings to load briefs.</div>` : visible.length ? visible.map(bountyCard).join("") : `<div class="loading">No bounties in this view yet.</div>`}</div><div class="detail-wrap">${detailPanel()}</div></div></section>
  <section class="create" id="create"><div class="create-copy"><p class="eyebrow lime">POST A BRIEF</p><h2>Make the question<br/><em>worth answering.</em></h2><p>Set the source standard up front. Your GEN stays locked until consensus settles the submission; unsubmitted work returns after its deadline.</p><div class="steps"><span><b>01</b> Brief</span><span><b>02</b> Evidence</span><span><b>03</b> Consensus</span></div></div><form id="create-form" class="form-card"><label>Title<input name="title" maxlength="120" required placeholder="e.g. Map the stablecoin payment landscape" /></label><label>Research brief<textarea name="brief" maxlength="4000" required placeholder="What should a contributor discover, compare, or verify?"></textarea></label><label>Success rubric<textarea name="rubric" maxlength="2400" required placeholder="What must be true for the work to earn the reward?"></textarea></label><div class="form-row"><label>Reward (GEN)<input name="reward" type="text" inputmode="decimal" pattern="^\\d+(\\.\\d{1,18})?$" required value="1" /></label><label>Deadline<select name="days"><option value="3">3 days</option><option value="7" selected>7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label></div><button class="primary wide" type="submit" ${state.pending ? "disabled" : ""}>Lock reward & publish <span>↗</span></button><small>Submitting opens a MetaMask confirmation. The wallet signs both the GEN reward and the GenLayer consensus request.</small></form></section>
      <section class="how"><div><p class="eyebrow">WHY IT WORKS</p><h2>Not a job board.<br/><em>A settlement layer.</em></h2></div><div class="how-grid"><div><span>01</span><h3>Clear intent</h3><p>A brief and rubric live with the escrow, so the task cannot quietly change mid-flight.</p></div><div><span>02</span><h3>Proof, not vibes</h3><p>Contributors submit a report plus URLs. Validators independently inspect the evidence.</p></div><div><span>03</span><h3>Consensus payout</h3><p>Approve pays the contributor, revise keeps the escrow open, reject refunds the customer.</p></div></div></section>
    </main><footer><span>sourcebounty / v0.1</span><span>GEN-native research settlement</span><button id="settings">Contract settings</button></footer>
    <div id="toast" class="toast ${state.error || state.message ? "show" : ""}">${esc(state.error || state.message)}</div>
  </div>`;
}

function render() {
  captureFormDrafts();
  document.querySelector("#app").innerHTML = appTemplate();
  restoreFormDrafts();
  bind();
}

function bind() {
  document.querySelector("#connect")?.addEventListener("click", () => connect().catch((e) => { state.error = e.message; render(); }));
  document.querySelector("#scroll-bounties")?.addEventListener("click", () => document.querySelector("#bounties")?.scrollIntoView({ behavior: "smooth" }));
  document.querySelectorAll("[data-filter]").forEach((el) => el.addEventListener("click", () => { state.filter = el.dataset.filter; render(); }));
  document.querySelectorAll("[data-bounty]").forEach((el) => el.addEventListener("click", async () => { try { const raw = await read("get_bounty", [el.dataset.bounty]); state.selected = typeof raw === "string" ? JSON.parse(raw) : raw; render(); } catch (e) { state.error = e.message; render(); } }));
  document.querySelector("#create-form")?.addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); try { await write("create_bounty", [form.get("title"), form.get("brief"), form.get("rubric"), BigInt(nowPlusDays(form.get("days")))], toWei(form.get("reward"))); clearFormDraft("create-form"); state.message = "Bounty published."; await refresh(); } catch (e) { state.error = e.message; state.pending = false; setToast(); } });
  document.querySelector("#submit-form")?.addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const evidence = String(form.get("evidence") || "").split("\n").map((u) => u.trim()).filter(Boolean); try { await write("submit_work", [state.selected.bounty_id, form.get("report"), JSON.stringify(evidence)]); clearFormDraft("submit-form"); state.submitOpen = false; await refresh(); } catch (e) { state.error = e.message; state.pending = false; setToast(); } });
  document.querySelector("#withdraw")?.addEventListener("click", async () => { try { await write("withdraw"); await refresh(); } catch (e) { state.error = e.message; state.pending = false; setToast(); } });
  document.querySelectorAll("[data-action]").forEach((el) => el.addEventListener("click", () => handleAction(el.dataset.action).catch((e) => { state.error = e.message; render(); })));
  document.querySelector("#settings")?.addEventListener("click", () => { const value = window.prompt("Deployed SourceBounty contract address", state.contract); if (value !== null) { state.contract = value.trim(); localStorage.setItem("sourcebounty.contract", state.contract); refresh(); } });
}

async function handleAction(action) {
  if (!state.selected) return;
  const id = state.selected.bounty_id;
  if (action === "claim") await write("claim_bounty", [id]);
  if (action === "cancel") await write("cancel_bounty", [id]);
  if (action === "expire") await write("expire_bounty", [id]);
  if (action === "evaluate") await write("evaluate_submission", [id]);
  if (action === "submit") { state.submitOpen = true; state.error = ""; render(); return; }
  if (action === "close-submit") { state.submitOpen = false; render(); return; }
  state.message = `${action} confirmed.`; await refresh();
}

render();
refresh();
