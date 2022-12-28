// https://stackoverflow.com/questions/14267781/sorting-html-table-with-javascript
// https://stackoverflow.com/questions/40201533/sort-version-dotted-number-strings-in-javascript
const getCellValue = (tr, idx) =>
  tr.children[idx].dataset.diff ||
  tr.children[idx].innerText ||
  tr.children[idx].textContent;
const padDotVersion = (dn) =>
  dn
    .split(".")
    .map((n) => +n + 1000)
    .join("");
const padDotVersionStr = (dn) => dn.replace(/\d+/g, (n) => +n + 1000);
let p1, p2;
const comparer = (idx, asc) => (a, b) =>
  ((v1, v2) =>
    v1 !== "" && v2 !== "" && !isNaN(v1) && !isNaN(v2)
      ? v1 - v2
      : v1 !== "" && v2 !== "" && !isNaN("0x" + v1) && !isNaN("0x" + v2)
      ? parseInt(v1, 16) - parseInt(v2, 16)
      : v1 !== "" &&
        v2 !== "" &&
        !isNaN((p1 = padDotVersion(v1))) &&
        !isNaN((p2 = padDotVersion(v2)))
      ? p1 - p2
      : v1 !== "" &&
        v2 !== "" &&
        !isNaN(padDotVersion(v1.replace("clang++ ", "").replace("g++ ", ""))) &&
        !isNaN(padDotVersion(v2.replace("clang++ ", "").replace("g++ ", "")))
      ? padDotVersionStr(v1).toString().localeCompare(padDotVersionStr(v2))
      : v1.toString().localeCompare(v2))(
    getCellValue(asc ? a : b, idx),
    getCellValue(asc ? b : a, idx)
  );

document.addEventListener("DOMContentLoaded", () => {
  document.addEventListener("click", (e) => {
    const { target } = e;
    if (target.matches("th")) {
      const th = target;
      const table = th.closest("table");
      const body = table.querySelector("tbody");
      Array.from(body.querySelectorAll("tr"))
        .sort(
          comparer(
            Array.from(th.parentNode.children).indexOf(th),
            (this.asc = !this.asc)
          )
        )
        .forEach((tr) => body.append(tr));
    }
  });

  // Click the sun/moon icons to change the color theme of the site
  // hash calculated by browser for sub-resource integrity checks:
  // https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
  const match = document.cookie.match(
    new RegExp("(^| )" + "theme" + "=([^;]+)")
  );

  const setTheme = (theme) => {
    if (theme === "dark") {
      document.getElementById("sun").style.display = "";
      document.getElementById("moon").style.display = "none";
      const link = document.createElement("link");
      link["rel"] = "stylesheet";
      link["href"] = "/css/theme.dark.css?v=" + darkThemeHash;
      link["integrity"] = "sha384-" + darkThemeHash;
      link["crossOrigin"] = "anonymous";
      document.querySelector("head").append(link);
    } else {
      document.getElementById("sun").style.display = "none";
      document.getElementById("moon").style.display = "";
      document
        .querySelector('head link[href*="/css/theme.dark.css"]')
        ?.remove();
    }
    // Remember the theme for 30 days
    document.cookie = `theme=${theme};path=/;max-age=${
      30 * 24 * 60 * 60
    };SameSite=Lax;`;
  };

  const getPreferredTheme = () => {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  };

  if (!match) {
    setTheme(getPreferredTheme());
  }

  try {
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", () => setTheme(getPreferredTheme()));
  } catch (e) {
    console.error(e);
  }

  document
    .getElementById("sun")
    .addEventListener("click", () => setTheme("light"));

  document
    .getElementById("moon")
    .addEventListener("click", () => setTheme("dark"));

  // CSRF protection for links and forms
  const csrfToken = document.querySelector("meta[name='csrf-token']")[
    "content"
  ];
  document.getElementById("logout")?.addEventListener("click", (e) => {
    e.preventDefault();
    fetch("/logout", {
      method: "POST",
      headers: {
        "X-CSRF-Token": csrfToken,
      },
    }).then(() => (window.location = "/"));
  });
  document.querySelectorAll("form[method='POST']")?.forEach((form) => {
    const input = document.createElement("input");
    input["type"] = "hidden";
    input["name"] = "csrf_token";
    input["value"] = csrfToken;
    form.append(input);
  });
});

function supportsNotifications() {
  if (
    // Safari on iOS doesn't support them
    "Notification" in window &&
    // Chrome and Opera on Android don't support them
    !(
      navigator.userAgent.match(/Android/i) &&
      navigator.userAgent.match(/Chrome/i)
    )
  )
    return true;
  return false;
}

function raise_for_status(response) {
  // A useful function from the python requests package
  if (response.ok) {
    return;
  }
  throw `request failed with status code ${response.status}`;
}

async function fetch_json(url) {
  const response = await fetch(url);
  raise_for_status(response);
  return response.json();
}

function DOM_loaded() {
  // Use as
  // await DOM_loaded();
  // in an async function.
  return new Promise((resolve, reject) => {
    if (document.readyState == "loading") {
      document.addEventListener("DOMContentLoaded", resolve);
    } else {
      resolve();
    }
  });
}

function async_sleep(ms) {
  return new Promise((resolve, reject) => {
    setTimeout(resolve, ms);
  });
}
