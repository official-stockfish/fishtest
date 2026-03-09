(async () => {
  await DOMContentLoaded();

  const filtersContainer = document.getElementById("active-run-filters");
  if (!filtersContainer) {
    return;
  }

  const cookieName = "active_run_filters";
  const cookieMaxAge = Number(
    filtersContainer.dataset.filterCookieMaxAge || "0",
  );

  const allCheckbox = document.getElementById("active-filter-all");
  const dimensions = ["test-type", "time-control", "threads"];
  const dimensionCheckboxes = {};

  for (const dim of dimensions) {
    dimensionCheckboxes[dim] = [
      ...filtersContainer.querySelectorAll(
        `input[type="checkbox"][data-dimension="${dim}"]`,
      ),
    ];
  }

  const allTypeCheckboxes = dimensions.flatMap(
    (dim) => dimensionCheckboxes[dim],
  );

  const tbody = document.getElementById("active-tbody");
  const countSpan = document.getElementById("active-count");
  const toggleBtn = document.getElementById("active-filter-toggle");
  const filterPanel = document.getElementById("active-filter-panel");

  if (
    !(allCheckbox instanceof HTMLInputElement) ||
    allTypeCheckboxes.length === 0 ||
    !tbody ||
    !(toggleBtn instanceof HTMLButtonElement) ||
    !(filterPanel instanceof HTMLElement)
  ) {
    return;
  }

  // Dynamic <style> element for CSS-based row filtering.
  // CSS attribute selectors survive htmx's 20 ms attribute-settle phase
  // (which would strip a class like d-none added by JS between the swap
  // and the settle timeout).
  const filterStyleEl = document.createElement("style");
  filterStyleEl.id = "active-run-filter-style";
  document.head.appendChild(filterStyleEl);

  // Cached filter state used by refreshCount().
  let currentEnabledByDim = {};
  let allFiltersEnabled = true;

  const restoreState = () => {
    const raw = getCookie(cookieName);
    if (!raw) {
      return;
    }
    const enabled = new Set(raw.split(","));
    for (const cb of allTypeCheckboxes) {
      cb.checked = enabled.has(cb.value);
    }
    syncAllCheckbox();
  };

  const persistState = () => {
    const allChecked = allTypeCheckboxes.every((cb) => cb.checked);
    if (allChecked) {
      clearCookie();
    } else {
      const enabled = allTypeCheckboxes
        .filter((cb) => cb.checked)
        .map((cb) => cb.value);
      setFilterCookie(enabled.join(","));
    }
  };

  const setFilterCookie = (value) => {
    if (!Number.isFinite(cookieMaxAge) || cookieMaxAge <= 0) {
      return;
    }
    document.cookie = `${cookieName}=${value}; path=/; max-age=${cookieMaxAge}; SameSite=Lax`;
  };

  const clearCookie = () => {
    document.cookie = `${cookieName}=; path=/; max-age=0; SameSite=Lax`;
  };

  const syncAllCheckbox = () => {
    const checkedCount = allTypeCheckboxes.filter((cb) => cb.checked).length;
    if (checkedCount === allTypeCheckboxes.length) {
      allCheckbox.checked = true;
      allCheckbox.indeterminate = false;
    } else if (checkedCount === 0) {
      allCheckbox.checked = false;
      allCheckbox.indeterminate = false;
    } else {
      allCheckbox.checked = false;
      allCheckbox.indeterminate = true;
    }
  };

  const applyFilters = () => {
    allFiltersEnabled = true;

    for (const dim of dimensions) {
      const cbs = dimensionCheckboxes[dim];
      const checked = cbs.filter((cb) => cb.checked).map((cb) => cb.value);
      currentEnabledByDim[dim] = new Set(checked);
      if (checked.length < cbs.length) {
        allFiltersEnabled = false;
      }
    }

    // Build CSS rules that hide rows whose data-* attribute matches an
    // unchecked value.  This is AND-of-ORs: a row failing ANY dimension
    // is hidden.
    if (allFiltersEnabled) {
      filterStyleEl.textContent = "";
    } else {
      const hide = [];
      for (const dim of dimensions) {
        for (const cb of dimensionCheckboxes[dim]) {
          if (!currentEnabledByDim[dim].has(cb.value)) {
            hide.push(`#active-tbody tr[data-${dim}="${cb.value}"]`);
          }
        }
      }
      filterStyleEl.textContent =
        hide.length > 0
          ? hide.join(",\n") + " { display: none !important; }"
          : "";
    }

    refreshCount();
  };

  const refreshCount = () => {
    if (!countSpan) {
      return;
    }
    const allRows = tbody.querySelectorAll("tr[data-test-type]");
    const totalRows = allRows.length;

    if (allFiltersEnabled) {
      countSpan.textContent = `Active - ${totalRows} tests`;
      return;
    }

    let visibleCount = 0;
    for (const row of allRows) {
      let match = true;
      for (const dim of dimensions) {
        if (!currentEnabledByDim[dim].has(row.getAttribute(`data-${dim}`))) {
          match = false;
          break;
        }
      }
      if (match) {
        visibleCount++;
      }
    }

    countSpan.textContent =
      visibleCount === totalRows
        ? `Active - ${totalRows} tests`
        : `Active - ${totalRows} (${visibleCount}) tests`;
  };

  allCheckbox.addEventListener("change", () => {
    for (const cb of allTypeCheckboxes) {
      cb.checked = allCheckbox.checked;
    }
    allCheckbox.indeterminate = false;
    applyFilters();
    persistState();
  });

  for (const cb of allTypeCheckboxes) {
    cb.addEventListener("change", () => {
      syncAllCheckbox();
      applyFilters();
      persistState();
    });
  }

  // After an OOB innerHTML swap the CSS rules still hide the right rows
  // (they target data-* attributes, immune to htmx settle).  We only need
  // to recompute the count text, because the server's count_updates OOB
  // overwrites our filtered count with the unfiltered total.
  new MutationObserver(() => {
    refreshCount();
  }).observe(tbody, { childList: true });

  // 3-dot toggle: show/hide the filter panel.  Cookie persists state.
  const toggleCookieName = "active_run_filters_panel";

  const setPanel = (visible) => {
    filterPanel.hidden = !visible;
    toggleBtn.setAttribute("aria-expanded", String(visible));
  };

  if (getCookie(toggleCookieName) === "hidden") {
    setPanel(false);
  }

  toggleBtn.addEventListener("click", () => {
    const isVisible = !filterPanel.hidden;
    setPanel(!isVisible);
    if (isVisible) {
      setStateCookie(toggleCookieName, "hidden", cookieMaxAge);
    } else {
      document.cookie = `${toggleCookieName}=; path=/; max-age=0; SameSite=Lax`;
    }
  });

  restoreState();
  applyFilters();
})();
