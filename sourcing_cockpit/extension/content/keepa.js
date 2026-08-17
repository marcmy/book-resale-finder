(async () => {
  const SC = globalThis.SourcingCockpit;
  if (!SC) return;

  const processed = new WeakSet();
  const state = {
    scanned: 0,
    sellable: 0,
    approval: 0,
    restricted: 0,
    errors: 0,
    pomodoroEnds: 0,
    pomodoroTimer: null
  };

  const settingsResponse = await chrome.runtime.sendMessage({ type: "GET_SETTINGS" });
  const settings = settingsResponse?.settings || {};

  const toolbar = createToolbar();
  document.documentElement.appendChild(toolbar);

  function rowFromElement(el) {
    return el.closest(
      "[role='row'], tr, .ag-row, .productRow, .product-row, .product, .tableRow, li"
    ) || el.parentElement?.parentElement || el.parentElement;
  }

  function discoverRows() {
    const out = new Map();

    document.querySelectorAll("[data-asin]").forEach(el => {
      const asin = SC.normalizeAsin(el.getAttribute("data-asin"));
      if (asin) out.set(rowFromElement(el), asin);
    });

    document.querySelectorAll("a[href]").forEach(a => {
      const asin = SC.asinFromUrl(a.href);
      if (!asin) return;
      const row = rowFromElement(a);
      if (row) out.set(row, asin);
    });

    return [...out.entries()].filter(([row]) => row && !processed.has(row));
  }

  function getRowMeta(row, asin) {
    const text = (row.innerText || "").replace(/\s+/g, " ").trim();
    const links = [...row.querySelectorAll("a[href]")];
    const titleLink = links.find(a => SC.asinFromUrl(a.href) === asin) || links.find(a => a.textContent?.trim().length > 8);
    const title = titleLink?.textContent?.trim() || text.slice(0, 180);
    const brandMatch = text.match(/\bbrand\s*[:\-]\s*([^|•]{2,60})/i);
    const categoryMatch = text.match(/\bcategory\s*[:\-]\s*([^|•]{2,60})/i);
    const sellerCount =
      SC.intAfterLabels(text, ["sellers", "seller", "offers", "offer count"]) ??
      Number(text.match(/\b([0-9]{1,3})\s+(?:sellers?|offers?)\b/i)?.[1] || NaN);
    const rank = SC.intAfterLabels(text, ["sales rank", "rank"]);
    const drops = SC.intAfterLabels(text, ["drops", "sales drops", "drop count"]);
    const price = SC.moneyFromText(text);

    return {
      asin,
      title,
      brand: brandMatch?.[1]?.trim() || "",
      category: categoryMatch?.[1]?.trim() || "",
      sellerCount: Number.isFinite(sellerCount) ? sellerCount : null,
      rank,
      drops,
      price,
      url: titleLink?.href || `https://www.amazon.com/dp/${asin}`,
      text
    };
  }

  function classifyFlags(meta) {
    const t = `${meta.title} ${meta.text}`.toLowerCase();
    const meltableWords = [
      "chocolate", "gummy", "gummies", "wax", "candle", "lipstick", "balm",
      "fudge", "caramel", "suppository"
    ];
    const hazmatWords = [
      "aerosol", "propane", "butane", "lithium", "battery", "batteries",
      "bleach", "paint", "solvent", "flammable", "compressed gas", "pesticide"
    ];
    const flags = [];
    if (meltableWords.some(x => t.includes(x))) flags.push("🌡️ melt?");
    if (hazmatWords.some(x => t.includes(x))) flags.push("⚠️ hazmat?");
    return flags;
  }

  function localDealScore(meta) {
    let score = 5;
    const reasons = [];

    if (Number.isFinite(meta.rank)) {
      if (meta.rank <= 50_000) { score += 2; reasons.push("strong rank"); }
      else if (meta.rank <= 150_000) { score += 1; reasons.push("good rank"); }
      else if (meta.rank >= 800_000) { score -= 2; reasons.push("weak rank"); }
      else if (meta.rank >= 350_000) { score -= 1; reasons.push("slower rank"); }
    }
    if (Number.isFinite(meta.drops)) {
      if (meta.drops >= 20) { score += 2; reasons.push("many drops"); }
      else if (meta.drops >= 8) { score += 1; reasons.push("some drops"); }
      else if (meta.drops <= 1) { score -= 1; reasons.push("few drops"); }
    }
    if (Number.isFinite(meta.sellerCount)) {
      if (meta.sellerCount <= 4) { score += 1; reasons.push("low competition"); }
      else if (meta.sellerCount >= 15) { score -= 2; reasons.push("high competition"); }
      else if (meta.sellerCount >= 9) { score -= 1; reasons.push("busy listing"); }
    }
    score = Math.max(1, Math.min(10, score));
    return { score, reasons };
  }

  function mountForRow(row) {
    let mount = row.querySelector(":scope > .sc-row-actions");
    if (mount) return mount;
    mount = document.createElement("span");
    mount.className = "sc-row-actions";
    const target = row.querySelector("td:last-child, [role='gridcell']:last-child") || row;
    target.appendChild(mount);
    return mount;
  }

  function button(label, title, onClick) {
    const b = document.createElement("button");
    b.className = "sc-mini";
    b.type = "button";
    b.textContent = label;
    b.title = title;
    b.addEventListener("click", onClick);
    return b;
  }

  async function toggleBookmark(meta, buttonEl) {
    const response = await chrome.runtime.sendMessage({ type: "GET_STATE", keys: ["bookmarks"] });
    const bookmarks = response?.state?.bookmarks || {};
    if (bookmarks[meta.asin]) {
      delete bookmarks[meta.asin];
      buttonEl.textContent = "☆";
    } else {
      bookmarks[meta.asin] = { ...meta, savedAt: Date.now() };
      buttonEl.textContent = "★";
    }
    await chrome.runtime.sendMessage({ type: "SET_STATE", state: { bookmarks } });
  }

  async function setCost(meta) {
    const response = await chrome.runtime.sendMessage({ type: "GET_STATE", keys: ["costs"] });
    const costs = response?.state?.costs || {};
    const current = costs[meta.asin]?.cost ?? "";
    const entered = prompt(`Cost for ${meta.asin}`, current);
    if (entered == null) return;
    const cost = Number(entered);
    if (!Number.isFinite(cost) || cost < 0) return alert("Enter a valid non-negative cost.");
    costs[meta.asin] = { cost, updatedAt: Date.now(), title: meta.title || "" };
    await chrome.runtime.sendMessage({ type: "SET_STATE", state: { costs } });
  }

  async function processRow(row, asin) {
    processed.add(row);
    row.dataset.scAsin = asin;
    const meta = getRowMeta(row, asin);
    const mount = mountForRow(row);

    const status = document.createElement("span");
    status.className = "sc-badge";
    status.dataset.status = "UNKNOWN";
    status.textContent = "checking…";
    status.title = "Seller-specific listing eligibility";
    mount.appendChild(status);

    const score = localDealScore(meta);
    const scoreBadge = document.createElement("span");
    scoreBadge.className = "sc-badge";
    scoreBadge.textContent = `Score ${score.score}/10`;
    scoreBadge.title = `Local heuristic, not SourceLens' proprietary score. ${score.reasons.join(", ") || "Limited row data."}`;
    mount.appendChild(scoreBadge);

    const flags = classifyFlags(meta);
    for (const flag of flags) {
      const el = document.createElement("span");
      el.className = "sc-badge";
      el.textContent = flag;
      el.title = "Keyword heuristic only; confirm in Amazon before sourcing.";
      mount.appendChild(el);
    }

    if (Number.isFinite(meta.sellerCount)) {
      const observed = await chrome.runtime.sendMessage({
        type: "OBSERVE_SELLERS",
        asin,
        sellerCount: meta.sellerCount
      });
      const trend = observed?.trend === "up" ? "↑ comp" : observed?.trend === "down" ? "↓ comp" : "→ comp";
      const trendBadge = document.createElement("span");
      trendBadge.className = "sc-badge";
      trendBadge.textContent = trend;
      trendBadge.title = "Competition trend based on seller counts observed locally over time.";
      mount.appendChild(trendBadge);
    }

    const bookmarkButton = button("☆", "Bookmark / Watch Later", e => toggleBookmark(meta, e.currentTarget));
    mount.appendChild(bookmarkButton);

    const costButton = button("$", "Set per-ASIN cost", () => setCost(meta));
    mount.appendChild(costButton);

    const similar = button("Similar", "Search Keepa using title keywords", () => {
      const q = SC.titleWords(meta.title).join(" ");
      window.open(`https://keepa.com/#!search/1/${encodeURIComponent(q)}`, "_blank", "noopener");
    });
    mount.appendChild(similar);

    const rabbit = button("Rabbit", "Search Amazon using a narrower title/brand trail", () => {
      const words = SC.titleWords(`${meta.brand} ${meta.title}`).slice(0, 5).join(" ");
      window.open(`https://www.amazon.com/s?k=${encodeURIComponent(words)}`, "_blank", "noopener");
    });
    mount.appendChild(rabbit);

    try {
      const eligibility = await chrome.runtime.sendMessage({
        type: "CHECK_ELIGIBILITY",
        asin
      });
      if (!eligibility?.ok) throw new Error(eligibility?.error || "Eligibility failed");

      const result = eligibility.result;
      status.dataset.status = result.status || "UNKNOWN";
      status.textContent =
        result.status === "SELLABLE" ? "● sellable" :
        result.status === "APPROVAL_REQUIRED" ? "● approval" :
        result.status === "RESTRICTED" ? "● restricted" :
        "● unknown";
      status.title = [
        result.message || "",
        result.source ? `Source: ${result.source}` : "",
        result.reasonCodes?.length ? `Reasons: ${result.reasonCodes.join(", ")}` : ""
      ].filter(Boolean).join("\n");

      if (result.approvalUrl) {
        status.style.cursor = "pointer";
        status.addEventListener("click", () => window.open(result.approvalUrl, "_blank", "noopener"));
      }

      state.scanned++;
      if (result.status === "SELLABLE") state.sellable++;
      else if (result.status === "APPROVAL_REQUIRED") state.approval++;
      else if (result.status === "RESTRICTED") state.restricted++;

      await chrome.runtime.sendMessage({
        type: "OBSERVE_GATING",
        observation: { ...meta, eligibility: result.status || "UNKNOWN" }
      });

      await chrome.runtime.sendMessage({
        type: "APPEND_HISTORY",
        entry: {
          ...meta,
          eligibility: result.status || "UNKNOWN",
          score: score.score,
          flags,
          observedAt: Date.now()
        }
      });
    } catch (error) {
      status.dataset.status = "ERROR";
      status.textContent = "● bridge?";
      status.title = String(error?.message || error);
      state.errors++;
    }

    updateToolbar();
    applyFilter();
  }

  async function scan() {
    const rows = discoverRows();
    for (const [row, asin] of rows) {
      processRow(row, asin);
      await new Promise(r => setTimeout(r, 35));
    }
    updateToolbar();
  }

  function createToolbar() {
    const el = document.createElement("div");
    el.id = "sc-toolbar";
    el.innerHTML = `
      <div class="sc-title">Sourcing Cockpit</div>
      <div class="sc-stat" id="sc-stats">Waiting for Keepa rows…</div>
      <div class="sc-line">
        <button class="sc-mini" id="sc-scan">Scan</button>
        <select id="sc-filter" title="Filter rows by seller eligibility">
          <option value="ALL">All</option>
          <option value="SELLABLE">Sellable</option>
          <option value="APPROVAL_REQUIRED">Approval</option>
          <option value="RESTRICTED">Restricted</option>
          <option value="UNKNOWN">Unknown/error</option>
        </select>
      </div>
      <div class="sc-line">
        <button class="sc-mini" id="sc-pomo">Start 25m</button>
        <span id="sc-pomo-clock">00:00</span>
        <button class="sc-mini" id="sc-export">History CSV</button>
      </div>
    `;
    el.querySelector("#sc-scan").addEventListener("click", scan);
    el.querySelector("#sc-filter").addEventListener("change", applyFilter);
    el.querySelector("#sc-pomo").addEventListener("click", startPomodoro);
    el.querySelector("#sc-export").addEventListener("click", exportHistory);
    return el;
  }

  function updateToolbar() {
    const stat = toolbar.querySelector("#sc-stats");
    stat.textContent = `${state.scanned} checked · ${state.sellable} sellable · ${state.approval} approval · ${state.restricted} restricted${state.errors ? ` · ${state.errors} errors` : ""}`;
  }

  function applyFilter() {
    const wanted = toolbar.querySelector("#sc-filter").value;
    document.querySelectorAll("[data-sc-asin]").forEach(row => {
      const status = row.querySelector(".sc-badge[data-status]")?.dataset.status || "UNKNOWN";
      const show =
        wanted === "ALL" ||
        status === wanted ||
        (wanted === "UNKNOWN" && (status === "UNKNOWN" || status === "ERROR"));
      row.classList.toggle("sc-hidden-by-filter", !show);
    });
  }

  async function exportHistory() {
    const response = await chrome.runtime.sendMessage({ type: "GET_STATE", keys: ["history"] });
    const history = response?.state?.history || [];
    const rows = [["ASIN","Title","Brand","Category","Eligibility","Price","SellerCount","Score","Flags","ObservedAt","URL"]];
    for (const x of history) {
      rows.push([
        x.asin, x.title, x.brand, x.category, x.eligibility, x.price,
        x.sellerCount, x.score, x.flags, new Date(x.observedAt).toISOString(), x.url
      ]);
    }
    SC.downloadCsv(`sourcing-history-${new Date().toISOString().slice(0,10)}.csv`, rows);
  }

  function startPomodoro() {
    if (state.pomodoroTimer) {
      clearInterval(state.pomodoroTimer);
      state.pomodoroTimer = null;
      state.pomodoroEnds = 0;
      toolbar.querySelector("#sc-pomo-clock").textContent = "00:00";
      toolbar.querySelector("#sc-pomo").textContent = "Start 25m";
      return;
    }
    state.pomodoroEnds = Date.now() + 25 * 60_000;
    toolbar.querySelector("#sc-pomo").textContent = "Stop";
    const tick = () => {
      const left = Math.max(0, state.pomodoroEnds - Date.now());
      const m = Math.floor(left / 60_000);
      const s = Math.floor((left % 60_000) / 1000);
      toolbar.querySelector("#sc-pomo-clock").textContent = `${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
      if (!left) {
        clearInterval(state.pomodoroTimer);
        state.pomodoroTimer = null;
        state.pomodoroEnds = 0;
        toolbar.querySelector("#sc-pomo").textContent = "Start 25m";
        document.title = `✓ Pomodoro — ${document.title}`;
        alert("Sourcing Pomodoro complete.");
      }
    };
    tick();
    state.pomodoroTimer = setInterval(tick, 1000);
  }

  const observer = new MutationObserver(() => {
    clearTimeout(observer._timer);
    observer._timer = setTimeout(scan, 250);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  if (settings.autoScan !== false) scan();
})();
