(async () => {
  await DOMContentLoaded();

  const button = document.getElementById("machines-button");
  const panel = document.getElementById("machines-panel");
  const target = document.getElementById("machines");
  const filtersForm = document.getElementById("machines-filters");

  if (
    !(button instanceof HTMLElement) ||
    !(panel instanceof HTMLElement) ||
    !(target instanceof HTMLElement)
  ) {
    return;
  }

  const toggleCookieMaxAge = Number(button.dataset.toggleCookieMaxAge || "0");

  const syncPanelState = (isExpanded) => {
    const nextState = isExpanded ? "Hide" : "Show";
    button.textContent = nextState;
    button.setAttribute("aria-expanded", String(isExpanded));
    if (Number.isFinite(toggleCookieMaxAge) && toggleCookieMaxAge > 0) {
      writeUiCookie("machines_state", nextState, toggleCookieMaxAge);
    }
  };

  const resetMachinesPage = () => {
    const pageInput = document.getElementById("machines_page");
    if (pageInput instanceof HTMLInputElement) {
      pageInput.value = "1";
    }
  };

  filtersForm?.addEventListener("input", (event) => {
    if (
      event.target instanceof HTMLElement &&
      event.target.id === "machines_q"
    ) {
      resetMachinesPage();
    }
  });

  filtersForm?.addEventListener("change", (event) => {
    if (
      event.target instanceof HTMLElement &&
      event.target.id === "machines_my_workers"
    ) {
      resetMachinesPage();
    }
  });

  panel.addEventListener("shown.bs.collapse", () => {
    syncPanelState(true);
    if (target.dataset.machinesLoaded !== "1") {
      target.dataset.machinesLoaded = "loading";
    }
    htmx.trigger(target, "machines:load");
  });

  panel.addEventListener("hidden.bs.collapse", () => {
    syncPanelState(false);
  });

  // #machines is both the requesting element and the swap target.
  target.addEventListener("htmx:before:request", () => {
    if (target.dataset.machinesLoaded !== "1") {
      target.dataset.machinesLoaded = "loading";
    }
  });

  // Match on the swap target: #machines is also filled by #machines-filters.
  // Details: docs/9-references.md (section: "Source versus target").
  onHtmxSwap(
    (swapped) => swapped.id === "machines",
    () => {
      target.dataset.machinesLoaded = "1";
    },
  );

  const restoreRetryState = () => {
    if (target.dataset.machinesLoaded !== "1") {
      target.dataset.machinesLoaded = "0";
    }
  };

  target.addEventListener("htmx:response:error", restoreRetryState);
  target.addEventListener("htmx:error", (event) => {
    // An abort arrives here too, and its replacement request is already in
    // flight.
    if (htmxRequestAborted(event)) {
      return;
    }
    restoreRetryState();
  });
})();
