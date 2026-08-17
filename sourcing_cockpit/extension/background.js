const DEFAULTS = {
  bridgeUrl: "http://127.0.0.1:8765",
  bridgeToken: "",
  marketplaceId: "ATVPDKIKX0DER",
  conditionType: "used_good",
  cacheTtlHours: 168,
  autoScan: true,
  gistSyncEnabled: false,
  gistId: "",
  gistToken: ""
};

const inflight = new Map();
let storageMutationQueue = Promise.resolve();

chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get("settings");
  await chrome.storage.local.set({ settings: { ...DEFAULTS, ...(stored.settings || {}) } });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender)
    .then(sendResponse)
    .catch(error => sendResponse({ ok: false, error: String(error?.message || error) }));
  return true;
});

function serializedStorage(work) {
  const task = storageMutationQueue.then(work, work);
  storageMutationQueue = task.catch(() => undefined);
  return task;
}

async function mutateStorageKey(key, fallback, mutator) {
  return serializedStorage(async () => {
    const currentResult = await chrome.storage.local.get(key);
    const current = currentResult[key] ?? fallback;
    const result = await mutator(current);
    await chrome.storage.local.set({ [key]: current });
    return result;
  });
}

async function getSettings() {
  const { settings = {} } = await chrome.storage.local.get("settings");
  return { ...DEFAULTS, ...settings };
}

async function setSettings(patch) {
  return serializedStorage(async () => {
    const { settings: stored = {} } = await chrome.storage.local.get("settings");
    const settings = { ...DEFAULTS, ...stored, ...patch };
    await chrome.storage.local.set({ settings });
    return settings;
  });
}

async function storageGet(key, fallback) {
  const result = await chrome.storage.local.get(key);
  return result[key] ?? fallback;
}

async function storageSet(key, value) {
  return serializedStorage(() => chrome.storage.local.set({ [key]: value }));
}

function cacheKey(asin, marketplaceId, conditionType) {
  return `${marketplaceId}|${conditionType || ""}|${asin}`;
}

function bridgeHeaders(settings, json = false) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  if (settings.bridgeToken) headers["X-Sourcing-Cockpit-Token"] = settings.bridgeToken;
  return headers;
}

async function pairBridge(bridgeUrl, code) {
  const cleanUrl = String(bridgeUrl || "").replace(/\/$/, "");
  if (!/^http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/i.test(cleanUrl)) {
    throw new Error("Pairing page is not a local Sourcing Cockpit helper URL");
  }
  if (!code) throw new Error("Pairing code is missing");

  const response = await fetch(`${cleanUrl}/pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code })
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok || !payload.token) {
    throw new Error(payload.error || `Pairing failed with HTTP ${response.status}`);
  }
  await setSettings({ bridgeUrl: cleanUrl, bridgeToken: String(payload.token) });
  return { bridgeUrl: cleanUrl };
}

async function checkEligibility(asin, force = false, marketplaceOverride = null) {
  const settings = await getSettings();
  const marketplaceId = marketplaceOverride || settings.marketplaceId;
  const key = cacheKey(asin, marketplaceId, settings.conditionType);
  const cache = await storageGet("eligibilityCache", {});
  const now = Date.now();
  const ttlMs = Math.max(1, Number(settings.cacheTtlHours) || 168) * 3600_000;
  const cached = cache[key];

  if (!force && cached && now - cached.cachedAt < ttlMs) {
    return { ...cached, source: "cache" };
  }

  if (inflight.has(key)) return inflight.get(key);

  const promise = (async () => {
    if (!settings.bridgeToken) {
      throw new Error("Browser extension is not paired. Use Pair browser from the Sourcing Cockpit tray app.");
    }
    const response = await fetch(`${settings.bridgeUrl.replace(/\/$/, "")}/eligibility`, {
      method: "POST",
      headers: bridgeHeaders(settings, true),
      body: JSON.stringify({
        asins: [asin],
        marketplaceIds: [marketplaceId],
        conditionType: settings.conditionType || null
      })
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Bridge returned HTTP ${response.status}`);
    }

    const item = payload.results?.[asin];
    if (!item) throw new Error(`Bridge returned no result for ${asin}`);

    const entry = { ...item, asin, marketplaceId, cachedAt: Date.now(), source: "live" };
    await mutateStorageKey("eligibilityCache", {}, current => {
      current[key] = entry;
    });
    return entry;
  })().finally(() => inflight.delete(key));

  inflight.set(key, promise);
  return promise;
}

async function appendHistory(entry) {
  const normalized = {
    asin: entry.asin,
    title: entry.title || "",
    brand: entry.brand || "",
    category: entry.category || "",
    eligibility: entry.eligibility || "UNKNOWN",
    price: entry.price ?? "",
    sellerCount: entry.sellerCount ?? "",
    score: entry.score ?? "",
    flags: Array.isArray(entry.flags) ? entry.flags.join("|") : (entry.flags || ""),
    url: entry.url || "",
    observedAt: entry.observedAt || Date.now()
  };

  await mutateStorageKey("history", [], history => {
    history.unshift(normalized);
    history.splice(2000);
  });
  return normalized;
}

async function observeSellerCount(asin, sellerCount) {
  if (!Number.isFinite(sellerCount)) return { trend: "unknown", delta: null };

  return mutateStorageKey("sellerObservations", {}, all => {
    const series = all[asin] || [];
    const previous = series.at(-1);
    series.push({ count: sellerCount, at: Date.now() });
    if (series.length > 30) series.splice(0, series.length - 30);
    all[asin] = series;

    if (!previous || !Number.isFinite(previous.count) || previous.count === 0) {
      return { trend: "flat", delta: 0 };
    }
    const delta = (sellerCount - previous.count) / previous.count;
    if (delta >= 0.1) return { trend: "up", delta };
    if (delta <= -0.1) return { trend: "down", delta };
    return { trend: "flat", delta };
  });
}

async function upsertGatingObservation(observation) {
  await mutateStorageKey("gatingDb", {}, db => {
    const keys = [];
    if (observation.brand) keys.push(`brand:${observation.brand.trim().toLowerCase()}`);
    if (observation.category) keys.push(`category:${observation.category.trim().toLowerCase()}`);

    for (const key of keys) {
      const current = db[key] || { counts: {}, lastSeenAt: 0, examples: [] };
      current.counts[observation.eligibility] = (current.counts[observation.eligibility] || 0) + 1;
      current.lastSeenAt = Date.now();
      current.examples = [
        { asin: observation.asin, title: observation.title || "", eligibility: observation.eligibility },
        ...(current.examples || []).filter(x => x.asin !== observation.asin)
      ].slice(0, 10);
      db[key] = current;
    }
  });
}

async function hasFirefoxGistConsent() {
  const permissionsApi = globalThis.browser?.permissions;
  if (!permissionsApi?.getAll) return true;

  const permissions = await permissionsApi.getAll();
  if (!Object.prototype.hasOwnProperty.call(permissions, "data_collection")) return true;
  const granted = new Set(permissions.data_collection || []);
  return granted.has("authenticationInfo") && granted.has("browsingActivity");
}

async function gistRequest(method, path, body) {
  const settings = await getSettings();
  if (!settings.gistToken) throw new Error("Gist token is not configured");
  if (!(await hasFirefoxGistConsent())) {
    throw new Error("Firefox data-sharing permission for Gist sync is not granted");
  }

  const response = await fetch(`https://api.github.com${path}`, {
    method,
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${settings.gistToken}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(body ? { "Content-Type": "application/json" } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.message || `GitHub HTTP ${response.status}`);
  return payload;
}

async function snapshotSyncState() {
  const state = await chrome.storage.local.get(["gatingDb", "bookmarks", "notes", "costs"]);
  return {
    schema: 1,
    exportedAt: new Date().toISOString(),
    gatingDb: state.gatingDb || {},
    bookmarks: state.bookmarks || {},
    notes: state.notes || {},
    costs: state.costs || {}
  };
}

async function gistPush() {
  const settings = await getSettings();
  if (!settings.gistSyncEnabled) throw new Error("Gist sync is disabled");
  const content = JSON.stringify(await snapshotSyncState(), null, 2);
  let gistId = settings.gistId;

  if (!gistId) {
    const created = await gistRequest("POST", "/gists", {
      description: "Sourcing Cockpit team sync",
      public: false,
      files: { "sourcing-cockpit.json": { content } }
    });
    gistId = created.id;
    await setSettings({ gistId });
  } else {
    await gistRequest("PATCH", `/gists/${encodeURIComponent(gistId)}`, {
      files: { "sourcing-cockpit.json": { content } }
    });
  }
  return { gistId };
}

async function gistPull() {
  const settings = await getSettings();
  if (!settings.gistSyncEnabled || !settings.gistId) throw new Error("Gist sync is not configured");
  const gist = await gistRequest("GET", `/gists/${encodeURIComponent(settings.gistId)}`);
  const file = gist.files?.["sourcing-cockpit.json"];
  if (!file?.content) throw new Error("Gist does not contain sourcing-cockpit.json");
  const remote = JSON.parse(file.content);
  if (remote.schema !== 1) throw new Error(`Unsupported sync schema ${remote.schema}`);

  await serializedStorage(async () => {
    const local = await chrome.storage.local.get(["gatingDb", "bookmarks", "notes", "costs"]);
    await chrome.storage.local.set({
      gatingDb: { ...(local.gatingDb || {}), ...(remote.gatingDb || {}) },
      bookmarks: { ...(local.bookmarks || {}), ...(remote.bookmarks || {}) },
      notes: { ...(local.notes || {}), ...(remote.notes || {}) },
      costs: { ...(local.costs || {}), ...(remote.costs || {}) }
    });
  });
  return { pulledAt: Date.now() };
}

async function handleMessage(message) {
  switch (message?.type) {
    case "GET_SETTINGS":
      return { ok: true, settings: await getSettings() };

    case "SET_SETTINGS":
      return { ok: true, settings: await setSettings(message.patch || {}) };

    case "PAIR_BRIDGE":
      return { ok: true, ...(await pairBridge(message.bridgeUrl, message.code)) };

    case "CHECK_ELIGIBILITY":
      return {
        ok: true,
        result: await checkEligibility(
          message.asin,
          Boolean(message.force),
          message.marketplaceId || null
        )
      };

    case "CLEAR_ELIGIBILITY_CACHE":
      await storageSet("eligibilityCache", {});
      return { ok: true };

    case "GET_STATE": {
      const keys = Array.isArray(message.keys) ? message.keys : [];
      const state = await chrome.storage.local.get(keys);
      return { ok: true, state };
    }

    case "SET_STATE":
      await serializedStorage(() => chrome.storage.local.set(message.state || {}));
      return { ok: true };

    case "APPEND_HISTORY":
      return { ok: true, entry: await appendHistory(message.entry || {}) };

    case "OBSERVE_SELLERS":
      return { ok: true, ...(await observeSellerCount(message.asin, Number(message.sellerCount))) };

    case "OBSERVE_GATING":
      await upsertGatingObservation(message.observation || {});
      return { ok: true };

    case "BRIDGE_HEALTH": {
      const settings = await getSettings();
      const response = await fetch(`${settings.bridgeUrl.replace(/\/$/, "")}/health`, {
        headers: bridgeHeaders(settings)
      });
      const payload = await response.json().catch(() => ({}));
      return {
        ok: response.ok && payload.ok,
        health: payload,
        paired: Boolean(settings.bridgeToken),
        error: response.ok ? payload.error : `HTTP ${response.status}`
      };
    }

    case "FEE_ESTIMATE": {
      const settings = await getSettings();
      if (!settings.bridgeToken) {
        throw new Error("Browser extension is not paired. Use Pair browser from the Sourcing Cockpit tray app.");
      }
      const marketplaceId = message.marketplaceId || settings.marketplaceId;
      const response = await fetch(`${settings.bridgeUrl.replace(/\/$/, "")}/fees`, {
        method: "POST",
        headers: bridgeHeaders(settings, true),
        body: JSON.stringify({
          asin: message.asin,
          marketplaceId,
          price: Number(message.price),
          shipping: Number(message.shipping || 0),
          isAmazonFulfilled: Boolean(message.isAmazonFulfilled)
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) throw new Error(payload.error || `Bridge HTTP ${response.status}`);
      return { ok: true, result: payload.result };
    }

    case "GIST_PUSH":
      return { ok: true, ...(await gistPush()) };

    case "GIST_PULL":
      return { ok: true, ...(await gistPull()) };

    default:
      throw new Error(`Unknown message type: ${message?.type}`);
  }
}