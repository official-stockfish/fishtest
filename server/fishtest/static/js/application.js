// A console log with time stamp and optional stack trace
function console_log(message, trace) {
  const d = new Date().toISOString();
  const message_ = `${d}: ${message}`;
  if (trace) {
    console.trace(message_);
  } else {
    console.log(message_);
  }
}

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
              !isNaN(
                padDotVersion(v1.replace("clang++ ", "").replace("g++ ", "")),
              ) &&
              !isNaN(
                padDotVersion(v2.replace("clang++ ", "").replace("g++ ", "")),
              )
            ? padDotVersionStr(v1)
                .toString()
                .localeCompare(padDotVersionStr(v2))
            : v1.toString().localeCompare(v2))(
    getCellValue(asc ? a : b, idx),
    getCellValue(asc ? b : a, idx),
  );

function filterTable(inputId, tableId, originalRows) {
  const input = document.getElementById(inputId).value.toLowerCase();
  const table = document.getElementById(tableId);
  const tbody = table.querySelector("tbody");
  let noDataRow = table.querySelector(".no-data");

  // Clear the table before filtering
  while (tbody.firstChild) {
    tbody.removeChild(tbody.firstChild);
  }

  let filteredRows = 0;

  originalRows.forEach((row) => {
    const cells = Array.from(row.querySelectorAll("td"));
    const found = cells.some((cell) => {
      const cellText = cell.textContent || cell.innerText;
      return cellText.toLowerCase().indexOf(input) > -1;
    });

    if (found) {
      tbody.appendChild(row.cloneNode(true));
      filteredRows++;
    }
  });

  if (filteredRows === 0 && input !== "") {
    // Create the no-data row dynamically if it doesn't exist
    if (!noDataRow) {
      noDataRow = document.createElement("tr");
      noDataRow.classList.add("no-data");
      const cell = document.createElement("td");
      cell.setAttribute("colspan", "20");
      cell.textContent = "No matching data found";
      noDataRow.appendChild(cell);
    }
    tbody.appendChild(noDataRow);
  }
}

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
            (this.asc = !this.asc),
          ),
        )
        .forEach((tr, index) => {
          const rankData = tr.querySelector("td.rank");
          if (rankData) {
            rankData.textContent = index + 1;
          }
          body.append(tr);
        });
    }
  });

  // Click the sun/moon icons to change the color theme of the site
  // hash calculated by browser for sub-resource integrity checks:
  // https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
  const match = document.cookie.match(
    new RegExp("(^| )" + "theme" + "=([^;]+)"),
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
    log_out();
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
    // Notifications only work over a secure connection
    window.location.protocol == "https:" &&
    // Safari on iOS doesn't support them
    "Notification" in window &&
    // Chrome and Opera on Android don't support them
    !(
      navigator.userAgent.match(/Android/i) &&
      navigator.userAgent.match(/Chrome/i)
    )
  ) {
    return true;
  }
  return false;
}

function notify(title, body, link, fallback) {
  // Instrumentation
  console_log(`Notification: title=${title} body=${body}`);
  if (supportsNotifications() && Notification.permission === "granted") {
    const notification = new Notification(title, {
      body: body,
      requireInteraction: true,
      icon: "https://tests.stockfishchess.org/img/stockfish.png",
    });
    notification.onclick = () => {
      window.open(link, "_blank");
    };
  } else if (fallback) {
    fallback(title, body, link);
  }
}

function raise_for_status(response) {
  // A useful function from the python requests package
  if (response.ok) {
    return;
  }
  throw `request failed with status code ${response.status}`;
}

async function fetch_json(url, options) {
  const response = await fetch(url, options);
  raise_for_status(response);
  return response.json();
}

async function fetch_post(url, payload) {
  const options = {
    method: "POST",
    mode: "cors",
    cache: "no-cache",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  };
  return fetch_json(url, options);
}

async function fetch_text(url, options) {
  const response = await fetch(url, options);
  raise_for_status(response);
  return response.text();
}

async function process_title(count) {
  // async because the document title is often set in javascript
  await DOM_loaded();
  let title = document.title;
  // check if there is already a number
  if (/\([\d]+\)/.test(title)) {
    // if so, remove it
    let idx = title.indexOf(" ");
    title = title.slice(idx + 1);
  }
  // add it again if necessary
  if (count > 0) {
    document.title = `(${count}) ${title}`;
  } else {
    document.title = title;
  }
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
    const t0 = Date.now();
    setTimeout(() => {
      const t1 = Date.now();
      resolve(t1 - t0);
    }, ms);
  });
}

async function log_out_() {
  const csrfToken = document.querySelector("meta[name='csrf-token']")[
    "content"
  ];

  await fetch("/logout", {
    method: "POST",
    headers: {
      "X-CSRF-Token": csrfToken,
    },
  });
  window.location = "/";
}

function log_out() {
  broadcast("log_out_");
}

// Execute a function in all connected tabs.
// See notifications.js for a usage example.

const fishtest_broadcast_key = "fishtest_broadcast";
let broadcast_dispatch = {
  log_out_: log_out_,
};

window.addEventListener("storage", (event) => {
  if (event.key == fishtest_broadcast_key) {
    const cmd = JSON.parse(event.newValue);
    const cmd_function = broadcast_dispatch[cmd["cmd"]];
    if (cmd_function) {
      if (cmd["arg"]) cmd_function(cmd["arg"]);
      else cmd_function();
    }
  }
});

function broadcast(cmd, arg) {
  const cmd_function = broadcast_dispatch[cmd];
  localStorage.setItem(
    fishtest_broadcast_key,
    JSON.stringify({ cmd: cmd, arg: arg, rnd: Math.random() }),
  );
  if (arg) cmd_function(arg);
  else cmd_function();
}

// serializing objects

function save_object(key, value) {
  const key_ = `__fishtest__${key}`;
  const value_ = JSON.stringify(value);
  localStorage.setItem(key_, value_);
}

function load_object(key) {
  const key_ = `__fishtest__${key}`;
  const value_ = localStorage.getItem(key_);
  return JSON.parse(value_);
}

function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;")
    .replace(/\n/g, "<br>");
}
