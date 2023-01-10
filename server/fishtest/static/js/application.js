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
  if (supportsNotifications() && Notification.permission === "granted") {
    const notification = new Notification(title, {
      body: body,
      requireInteraction: true,
      icon: "https://tests.stockfishchess.org/img/stockfish.png",
    });
    notification.onclick = () => {
      window.location = link;
    };
  } else if (fallback) {
    fallback(title, body, link);
  } else {
    console.log("Notification: title=" + title + " body=" + body);
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
    setTimeout(resolve, ms);
  });
}

const fishtest_broadcast_key = "fishtest_broadcast";
let broadcast_dispatch = {};

window.addEventListener("storage", (event) => {
  if (event.key == fishtest_broadcast_key) {
    const cmd = JSON.parse(event.newValue);
    const cmd_function = broadcast_dispatch[cmd["cmd"]];
    if (cmd_function) {
      cmd_function(cmd["arg"]);
    }
  }
});

function broadcast(cmd, arg) {
  const cmd_function = broadcast_dispatch[cmd];
  cmd_function(arg);
  localStorage.setItem(
    fishtest_broadcast_key,
    JSON.stringify({ cmd: cmd, arg: arg, rnd: Math.random() })
  );
}

const tab_id = String(Math.random()).slice(2) + String(Math.random()).slice(2);

async function critical_section(lock, critical_section_) {
  // This is the simplest mutual exclusion algorithm not depending on
  // locking primitives. It is due to Michael Fischer and is mentioned in
  // Leslie Lamport's seminal paper "A Fast Mutual Exclusion Algorithm".
  // Lamport regards the algorithm as inadequate since we cannot
  // rigorously bound the delay necessary to execute (1)(2)(3) because
  // there is no bound on memory contention (here corresponding to the
  // setItem instructions). However for us this is not an issue -
  // 30ms should be sufficient for plenty of tabs.
  // Another issue is that taking the lock always takes at least 30ms
  // (with this implementation) even if there is no contention. This is also
  // not a problem since our application is not time critical.
  while (true) {
    let X;
    // We wait for the lock to clear. After 1.5s we assume that the current
    // holder of the lock has disappeared.
    for (let i = 0; i <= 50; i++) {
      X = localStorage.getItem(lock);
      // (1)
      if (X == null || X == "free") {
        break; // (2)
      }
      async_sleep(30);
    }
    // Ok the lock is clear. Let's try to grab it. Of course competing tabs will now do the same.
    localStorage.setItem(lock, tab_id); // (3)
    async_sleep(30); // Should be long enough to do (1)(2)(3) (by other tabs)
    X = localStorage.getItem(lock);
    if (X == tab_id) {
      // Hurray we won the race with the other tabs! Go to the critical section.
      break;
    }
    // Some other tab beat us. Let's try again.
  }
  // Let's allow for the possibility that the critical section is async...
  await critical_section_();
  localStorage.setItem(lock, "free"); // Release the lock.
}
