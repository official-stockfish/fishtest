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
  const filterStyleEl = (() => {
    const existing = document.getElementById("active-run-filter-style");
    if (existing instanceof HTMLStyleElement) {
      return existing;
    }
    const styleEl = document.createElement("style");
    styleEl.id = "active-run-filter-style";
    document.head.appendChild(styleEl);
    return styleEl;
  })();

  // Cached filter state used by refreshCount().
  let currentEnabledByDim = {};
  let allFiltersEnabled = true;
  let canonicalRows = [];
  let isApplyingFilters = false;
  let initialApplyPending = true;

  const buildFilterStyleText = (disabledSelectors) => {
    if (disabledSelectors.length === 0) {
      return "";
    }

    const hiddenRows = disabledSelectors.map(
      (selector) => `#active-tbody tr${selector}`,
    );
    return `${hiddenRows.join(",\n")} { display: none !important; }`;
  };

  const rowSortIndex = (row, fallbackIndex) => {
    const rawIndex = row.dataset.activeFilterIndex;
    const parsedIndex = Number(rawIndex);
    return Number.isFinite(parsedIndex) ? parsedIndex : fallbackIndex;
  };

  const syncCanonicalRows = () => {
    canonicalRows = [...tbody.querySelectorAll("tr[data-test-type]")].sort(
      (left, right) => rowSortIndex(left, 0) - rowSortIndex(right, 0),
    );
  };

  const restoreState = () => {
    const raw = getCookie(cookieName);
    if (!raw) {
      return;
    }
    if (raw === "none") {
      for (const cb of allTypeCheckboxes) {
        cb.checked = false;
      }
      syncAllCheckbox();
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
      setFilterCookie(enabled.length > 0 ? enabled.join(",") : "none");
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

    const disabledSelectors = [];
    if (allFiltersEnabled) {
      filterStyleEl.textContent = "";
    } else {
      for (const dim of dimensions) {
        for (const cb of dimensionCheckboxes[dim]) {
          if (!currentEnabledByDim[dim].has(cb.value)) {
            disabledSelectors.push(`[data-${dim}="${cb.value}"]`);
          }
        }
      }
      filterStyleEl.textContent = buildFilterStyleText(disabledSelectors);
    }

    if (canonicalRows.length === 0) {
      syncCanonicalRows();
    }

    const visibleRows = [];
    const hiddenRows = [];

    for (const row of canonicalRows) {
      let match = true;
      for (const dim of dimensions) {
        if (!currentEnabledByDim[dim].has(row.getAttribute(`data-${dim}`))) {
          match = false;
          break;
        }
      }

      row.hidden = !match;
      if (match) {
        visibleRows.push(row);
      } else {
        hiddenRows.push(row);
      }
    }

    const desiredRows = [...visibleRows, ...hiddenRows];
    const currentRows = [...tbody.querySelectorAll("tr[data-test-type]")];
    const orderChanged =
      desiredRows.length !== currentRows.length ||
      desiredRows.some((row, index) => row !== currentRows[index]);

    if (orderChanged) {
      const reorder = () => {
        const fragment = document.createDocumentFragment();
        for (const row of desiredRows) {
          fragment.appendChild(row);
        }
        isApplyingFilters = true;
        tbody.appendChild(fragment);
        isApplyingFilters = false;
      };
      if (initialApplyPending) {
        requestAnimationFrame(reorder);
      } else {
        reorder();
      }
    }
    initialApplyPending = false;

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

    countSpan.textContent = `Active - ${totalRows} (${visibleCount}) tests`;
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

  // After an OOB innerHTML swap we need to rebuild the canonical server order
  // for the new rows and then reapply the current filter state so the visible
  // rows remain contiguous and keep normal table-striped behavior.
  new MutationObserver(() => {
    if (isApplyingFilters) {
      return;
    }
    syncCanonicalRows();
    applyFilters();
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
  syncCanonicalRows();
  applyFilters();
})();
