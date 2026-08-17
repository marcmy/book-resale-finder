(async () => {
  if (location.pathname !== "/pair") return;

  const status = document.getElementById("sc-pair-status");
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  const code = params.get("code") || "";

  if (!code) {
    if (status) status.textContent = "Pairing code is missing. Start pairing again from the Sourcing Cockpit tray app.";
    return;
  }

  try {
    const result = await chrome.runtime.sendMessage({
      type: "PAIR_BRIDGE",
      bridgeUrl: location.origin,
      code
    });
    if (!result?.ok) throw new Error(result?.error || "Pairing failed");

    history.replaceState(null, "", location.pathname);
    if (status) {
      status.textContent = "✓ Browser extension paired successfully. You can close this tab and return to Keepa.";
    }
    document.title = "Sourcing Cockpit — Paired";
  } catch (error) {
    if (status) {
      status.textContent = `Pairing failed: ${String(error?.message || error)}`;
    }
  }
})();