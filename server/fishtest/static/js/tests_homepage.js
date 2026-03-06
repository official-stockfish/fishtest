(async () => {
  await DOMContentLoaded();

  const button = document.getElementById("machines-button");
  const target = document.getElementById("machines");
  const filtersForm = document.getElementById("machines-filters");

  if (!(button instanceof HTMLElement) || !(target instanceof HTMLElement)) {
    return;
  }

  const toggleCookieMaxAge = Number(button.dataset.toggleCookieMaxAge || "0");

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

  button.addEventListener("click", () => {
    const active = button.textContent.trim() === "Hide";
    const nextState = active ? "Show" : "Hide";

    button.textContent = nextState;
    if (Number.isFinite(toggleCookieMaxAge) && toggleCookieMaxAge > 0) {
      document.cookie = `machines_state=${nextState}; path=/; max-age=${toggleCookieMaxAge}; SameSite=Lax`;
    }

    if (!active && target.dataset.machinesLoaded !== "1") {
      target.dataset.machinesLoaded = "loading";
      htmx.trigger(target, "machines:load");
    }
  });

  target.addEventListener("htmx:beforeRequest", () => {
    if (target.dataset.machinesLoaded !== "1") {
      target.dataset.machinesLoaded = "loading";
    }
  });

  target.addEventListener("htmx:afterSwap", () => {
    target.dataset.machinesLoaded = "1";
  });

  const restoreRetryState = () => {
    if (target.dataset.machinesLoaded !== "1") {
      target.dataset.machinesLoaded = "0";
    }
  };

  target.addEventListener("htmx:responseError", restoreRetryState);
  target.addEventListener("htmx:sendError", restoreRetryState);
})();
