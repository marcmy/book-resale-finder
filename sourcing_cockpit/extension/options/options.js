(async () => {
  const SC = globalThis.SourcingCockpit;
  const ids = [
    "bridgeUrl", "marketplaceId", "conditionType", "cacheTtlHours",
    "autoScan", "gistSyncEnabled", "gistId", "gistToken"
  ];

  const response = await chrome.runtime.sendMessage({ type: "GET_SETTINGS" });
  const settings = response?.settings || {};

  for (const id of ids) {
    const el = document.getElementById(id);
    if (el.type === "checkbox") el.checked = Boolean(settings[id]);
    else el.value = settings[id] ?? "";
  }

  async function ensureFirefoxGistConsent() {
    const firefoxPermissions = globalThis.browser?.permissions;
    if (!firefoxPermissions?.request) return true;

    const request = {
      data_collection: ["authenticationInfo", "browsingActivity"]
    };

    try {
      if (firefoxPermissions.contains && await firefoxPermissions.contains(request)) return true;
      return Boolean(await firefoxPermissions.request(request));
    } catch (error) {
      console.warn("Could not request Firefox Gist-sync consent", error);
      return false;
    }
  }

  document.querySelector("#gistSyncEnabled").addEventListener("change", async e => {
    if (!e.target.checked) return;
    const granted = await ensureFirefoxGistConsent();
    if (!granted) {
      e.target.checked = false;
      alert("Firefox permission was not granted, so Gist sync will stay disabled.");
    }
  });

  document.querySelector("#save").addEventListener("click", async () => {
    if (document.querySelector("#gistSyncEnabled").checked) {
      const granted = await ensureFirefoxGistConsent();
      if (!granted) {
        document.querySelector("#gistSyncEnabled").checked = false;
      }
    }

    const patch = {};
    for (const id of ids) {
      const el = document.getElementById(id);
      patch[id] = el.type === "checkbox" ? el.checked : el.value;
    }
    patch.cacheTtlHours = Number(patch.cacheTtlHours) || 168;
    const result = await chrome.runtime.sendMessage({ type: "SET_SETTINGS", patch });
    document.querySelector("#saved").textContent = result?.ok ? "Saved." : (result?.error || "Save failed.");
  });

  document.querySelector("#health").addEventListener("click", async () => {
    const out = document.querySelector("#healthResult");
    out.textContent = "Checking…";
    const result = await chrome.runtime.sendMessage({ type: "BRIDGE_HEALTH" });
    out.textContent = result?.ok
      ? `Online · seller ${result.health?.sellerIdMasked || "configured"}`
      : (result?.error || "Offline");
  });

  document.querySelector("#costFile").addEventListener("change", async e => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split(/\r?\n/).filter(Boolean);
    if (!lines.length) return;
    const headers = parseCsvLine(lines[0]).map(x => x.trim().toLowerCase());
    const asinIndex = headers.indexOf("asin");
    const costIndex = headers.indexOf("cost");
    if (asinIndex < 0 || costIndex < 0) return alert("CSV must contain ASIN and cost columns.");

    const state = await chrome.runtime.sendMessage({ type: "GET_STATE", keys: ["costs"] });
    const costs = state?.state?.costs || {};
    let imported = 0;
    for (const line of lines.slice(1)) {
      const cols = parseCsvLine(line);
      const asin = SC.normalizeAsin(cols[asinIndex]);
      const cost = Number(cols[costIndex]);
      if (!asin || !Number.isFinite(cost) || cost < 0) continue;
      costs[asin] = { cost, updatedAt: Date.now() };
      imported++;
    }
    await chrome.runtime.sendMessage({ type: "SET_STATE", state: { costs } });
    alert(`Imported ${imported} costs.`);
    e.target.value = "";
  });

  document.querySelector("#exportCosts").addEventListener("click", async () => {
    const state = await chrome.runtime.sendMessage({ type: "GET_STATE", keys: ["costs"] });
    const rows = [["ASIN", "cost", "title", "updatedAt"]];
    for (const [asin, x] of Object.entries(state?.state?.costs || {})) {
      rows.push([asin, x.cost, x.title || "", x.updatedAt ? new Date(x.updatedAt).toISOString() : ""]);
    }
    SC.downloadCsv(`sourcing-costs-${new Date().toISOString().slice(0,10)}.csv`, rows);
  });

  function parseCsvLine(line) {
    const out = [];
    let field = "";
    let quoted = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') {
        if (quoted && line[i + 1] === '"') { field += '"'; i++; }
        else quoted = !quoted;
      } else if (c === "," && !quoted) {
        out.push(field);
        field = "";
      } else {
        field += c;
      }
    }
    out.push(field);
    return out;
  }
})();
