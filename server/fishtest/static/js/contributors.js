(async () => {
  await DOMContentLoaded();

  const form = document.getElementById("search_contributors_form");
  if (!(form instanceof HTMLFormElement)) {
    return;
  }

  const cookieName = form.dataset.findmeCookieName || "contributors_findme";
  const cookieMaxAge = Number(form.dataset.findmeCookieMaxAge || "0");
  const findme = document.getElementById("findme_contributors");
  const search = document.getElementById("search_contributors");

  const setFindmeCookie = (value) => {
    if (!Number.isFinite(cookieMaxAge) || cookieMaxAge <= 0) {
      return;
    }
    document.cookie = `${cookieName}=${value}; path=/; max-age=${cookieMaxAge}; SameSite=Lax`;
    document.cookie = `${cookieName}=${value}; path=/contributors; max-age=${cookieMaxAge}; SameSite=Lax`;
  };

  const getLatestCookie = (name) => {
    const key = `${name}=`;
    const matches = document.cookie
      .split(";")
      .map((part) => part.trim())
      .filter((part) => part.startsWith(key));
    const match = matches.length ? matches[matches.length - 1] : "";
    return match ? match.slice(key.length) : "";
  };

  const centerHighlightedContributor = () => {
    const target = document.getElementById("me");
    if (target && !target.classList.contains("d-none")) {
      target.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "nearest",
      });
    }
  };

  if (
    findme instanceof HTMLInputElement &&
    search instanceof HTMLInputElement
  ) {
    const params = new URLSearchParams(window.location.search);
    const findmeFromUrl = params.get("findme") === "1";
    const remembered = getLatestCookie(cookieName);

    if (remembered === "false") {
      findme.checked = false;
    } else if (findmeFromUrl) {
      findme.checked = true;
      setFindmeCookie("true");
      search.value = "";
    } else if (remembered === "true") {
      findme.checked = true;
      search.value = "";
    }

    findme.addEventListener("change", () => {
      if (findme.checked) {
        search.value = "";
      }
      setFindmeCookie(findme.checked ? "true" : "false");
    });

    const clearFindmeOnSearchInput = () => {
      if (!search.value.trim()) {
        return;
      }
      if (findme.checked) {
        findme.checked = false;
      }
      setFindmeCookie("false");
    };

    search.addEventListener("input", clearFindmeOnSearchInput);
    search.addEventListener("search", clearFindmeOnSearchInput);

    const highlightedRow = document.getElementById("me");
    const hasRenderedHighlight =
      highlightedRow && !highlightedRow.classList.contains("d-none");
    if (findme.checked && !hasRenderedHighlight) {
      if (typeof form.requestSubmit === "function") {
        requestAnimationFrame(() => form.requestSubmit());
      } else if (window.htmx) {
        htmx.trigger(findme, "change");
      }
    }
  }

  requestAnimationFrame(centerHighlightedContributor);
  window.addEventListener("load", centerHighlightedContributor, { once: true });
  window.addEventListener("hashchange", centerHighlightedContributor);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      centerHighlightedContributor();
    }
  });
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.target && event.target.id === "contributors-content") {
      requestAnimationFrame(centerHighlightedContributor);
    }
  });
})();
