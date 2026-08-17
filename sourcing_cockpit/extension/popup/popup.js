(async () => {
  const health = document.querySelector("#health");
  const msg = document.querySelector("#message");

  async function refresh() {
    const [state, bridge] = await Promise.all([
      chrome.runtime.sendMessage({ type: "GET_STATE", keys: ["bookmarks", "gatingDb", "history"] }),
      chrome.runtime.sendMessage({ type: "BRIDGE_HEALTH" })
    ]);
    document.querySelector("#bookmarks").textContent = Object.keys(state?.state?.bookmarks || {}).length;
    document.querySelector("#gates").textContent = Object.keys(state?.state?.gatingDb || {}).length;
    document.querySelector("#history").textContent = (state?.state?.history || []).length;
    health.textContent = bridge?.ok
      ? `Bridge online · ${bridge.health?.marketplaceId || "configured"}`
      : `Bridge offline · ${bridge?.error || "check Options"}`;
  }

  document.querySelector("#clear-cache").addEventListener("click", async () => {
    await chrome.runtime.sendMessage({ type: "CLEAR_ELIGIBILITY_CACHE" });
    msg.textContent = "Eligibility cache cleared.";
  });

  document.querySelector("#options").addEventListener("click", () => chrome.runtime.openOptionsPage());

  document.querySelector("#push").addEventListener("click", async () => {
    msg.textContent = "Pushing…";
    const r = await chrome.runtime.sendMessage({ type: "GIST_PUSH" });
    msg.textContent = r?.ok ? `Pushed · ${r.gistId}` : (r?.error || "Push failed");
  });

  document.querySelector("#pull").addEventListener("click", async () => {
    msg.textContent = "Pulling…";
    const r = await chrome.runtime.sendMessage({ type: "GIST_PULL" });
    msg.textContent = r?.ok ? "Pulled and merged." : (r?.error || "Pull failed");
    if (r?.ok) refresh();
  });

  refresh();
})();
