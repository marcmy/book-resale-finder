(() => {
  // Firefox exposes Promise-first WebExtension APIs as `browser.*` while
  // Chromium uses `chrome.*`. The rest of the extension intentionally uses
  // the Chromium spelling; on Firefox, point that spelling at `browser` so
  // our async/await calls behave identically.
  if (globalThis.browser) {
    try {
      globalThis.chrome = globalThis.browser;
    } catch (_) {
      // Extremely defensive fallback; current Firefox extension globals allow
      // this assignment. If that ever changes, callers still get native chrome.*.
    }
  }

  const MARKETPLACES = Object.freeze({
    ATVPDKIKX0DER: { amazonHost: "www.amazon.com", keepaDomain: 1, currency: "USD", currencySymbol: "$" },
    A2EUQ1WTGCTBG2: { amazonHost: "www.amazon.ca", keepaDomain: 6, currency: "CAD", currencySymbol: "$" },
    A1F83G8C2ARO7P: { amazonHost: "www.amazon.co.uk", keepaDomain: 2, currency: "GBP", currencySymbol: "£" }
  });

  function normalizeAsin(value) {
    if (!value) return null;
    const text = String(value).trim().toUpperCase();
    if (/^[A-Z0-9]{10}$/.test(text)) return text;

    // In arbitrary surrounding text, stay conservative: normal Amazon ASINs
    // generally begin with B, while ISBN-10 identifiers may end in X.
    const match = text.match(/\b(?:B[0-9A-Z]{9}|[0-9]{9}[0-9X])\b/);
    return match ? match[0] : null;
  }

  function asinFromUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(value, location.href);
      const candidates = [
        url.pathname.match(/\/(?:dp|gp\/product|product)\/([A-Z0-9]{10})(?:[/?]|$)/i)?.[1],
        url.searchParams.get("asin"),
        url.searchParams.get("ASIN")
      ];
      for (const candidate of candidates) {
        const asin = normalizeAsin(candidate);
        if (asin) return asin;
      }
    } catch (_) {}
    return normalizeAsin(value);
  }

  function marketplaceInfo(marketplaceId) {
    return MARKETPLACES[marketplaceId] || MARKETPLACES.ATVPDKIKX0DER;
  }

  function marketplaceFromHostname(hostname = location.hostname) {
    const host = String(hostname || "").toLowerCase();
    if (host.endsWith("amazon.co.uk")) return "A1F83G8C2ARO7P";
    if (host.endsWith("amazon.ca")) return "A2EUQ1WTGCTBG2";
    return "ATVPDKIKX0DER";
  }

  function csvEscape(value) {
    const s = value == null ? "" : String(value);
    return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  }

  function downloadCsv(filename, rows) {
    const csv = rows.map(row => row.map(csvEscape).join(",")).join("\r\n") + "\r\n";
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function moneyFromText(text) {
    const m = String(text || "").match(/(?:US\$|CA\$|C\$|\$|£)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)/i);
    return m ? Number(m[1].replaceAll(",", "")) : null;
  }

  function intAfterLabels(text, labels) {
    const escaped = labels.map(x => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
    const re = new RegExp(`(?:${escaped})\\s*[:#-]?\\s*([0-9][0-9,]*)`, "i");
    const match = String(text || "").match(re);
    return match ? Number(match[1].replaceAll(",", "")) : null;
  }

  function titleWords(title) {
    return String(title || "")
      .replace(/[^\p{L}\p{N}\s-]/gu, " ")
      .split(/\s+/)
      .filter(x => x.length >= 3)
      .slice(0, 8);
  }

  globalThis.SourcingCockpit = {
    normalizeAsin,
    asinFromUrl,
    marketplaceInfo,
    marketplaceFromHostname,
    csvEscape,
    downloadCsv,
    moneyFromText,
    intAfterLabels,
    titleWords
  };
})();
