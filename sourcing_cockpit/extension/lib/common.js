(() => {
  const ASIN_RE = /\b(B[0-9A-Z]{9}|[0-9]{10})\b/i;

  function normalizeAsin(value) {
    if (!value) return null;
    const match = String(value).toUpperCase().match(ASIN_RE);
    return match ? match[1] : null;
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
    const m = String(text || "").match(/\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)/);
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
    csvEscape,
    downloadCsv,
    moneyFromText,
    intAfterLabels,
    titleWords
  };
})();
