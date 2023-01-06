function LRU(capacity, content) {
  if (!content) {
    content = [];
  }
  if (typeof capacity != "number") {
    throw "capacity is not a number";
  }
  if (!(content instanceof Array)) {
    throw "content is not am Array";
  }
  return {
    capacity: capacity,
    content: content,
    count() {
      return this.content.length;
    },
    add(elt) {
      if (this.contains(elt)) {
        return;
      } else {
        this.content.push(elt);
        if (this.content.length > this.capacity) {
          this.content.shift();
        }
      }
    },
    contains(elt) {
      return this.content.findIndex((x) => x == elt) != -1;
    },
    save(name) {
      localStorage.setItem(name, JSON.stringify(this));
    },
    remove(elt) {
      idx = this.content.findIndex((x) => x == elt);
      if (idx == -1) {
        return;
      } else {
        this.content.splice(idx, 1);
      }
    },
  };
}

LRU.load = function (name) {
  let json = JSON.parse(localStorage.getItem(name));
  return new LRU(json["capacity"], json["content"]);
};

const fishtest_notifications_key = "fishtest_notifications";
const fishtest_broadcast_key = "fishtest_broadcast";

function notify_fishtest_(message) {
  const div = document.getElementById("fallback_div");
  const span = document.getElementById("fallback");
  const fallback_div = document.getElementById("fallback_div");
  if (fallback_div.style.display == "none") {
    span.innerHTML = message;
  } else {
    span.innerHTML += "<hr> " + title + " " + body;
  }
  div.style.display = "block";
}

function notify_fishtest(message) {
  notify_fishtest_(message);
  broadcast_fishtest(message);
}

function broadcast_fishtest(message) {
  localStorage.setItem(
    fishtest_broadcast_key,
    JSON.stringify({ message: message, rnd: Math.random() })
  );
}

window.addEventListener("storage", (event) => {
  if (event.key == fishtest_broadcast_key) {
    notify_fishtest_(JSON.parse(event.newValue)["message"]);
  }
});

function notify_elo(entry) {
  const tag = entry["run"].slice(0, -8);
  const message = entry["message"];
  const username = entry["username"];
  const color = message.split(" ")[0].split(":")[1];
  const elo = message.split(" ")[1];
  const LOS = message.split(" ")[2];
  const title = `Test ${tag} by ${username} finished ${color}!`;
  const body = elo + " " + LOS;
  notify(title, body, (title, body) => {
    notify_fishtest(title + " " + body);
  });
}

function get_notifications() {
  try {
    let lru = LRU.load(fishtest_notifications_key);
    if (lru["capacity"] != 15) {
      throw "";
    }
    return lru;
  } catch (e) {
    console.log("Initializing new LRU object");
    let notifications = new LRU(15);
    notifications.save(fishtest_notifications_key);
    return notifications;
  }
}

function save_notifications(notifications) {
  notifications.save(fishtest_notifications_key);
}

async function main_follow_loop() {
  await DOM_loaded();
  async_sleep(10000);
  while (true) {
    let json;
    let notifications = get_notifications();
    try {
      json = await fetch_post("/api/actions", {
        action: "finished_run",
        run_id: { $in: notifications.content },
      });
    } catch (e) {
      console.log(e);
      await async_sleep(20000);
      continue;
    }
    notifications = get_notifications();
    let work = [];
    json.forEach((entry) => {
      let run_id = entry["run_id"];
      if (notifications.contains(run_id)) {
        work.push(entry);
        notifications.remove(run_id);
      }
    });
    save_notifications(notifications);
    // Instrumentation
    console.log("active notifications: ", JSON.stringify(notifications));
    work.forEach((entry) => {
      notify_elo(entry);
      if (typeof page_id != "undefined" && page_id == entry["run_id"]) {
        button = document.getElementById("follow_elo");
        button.style.display = "none";
      }
    });
    await async_sleep(20000);
  }
}

function follow_run(run_id) {
  let notifications = get_notifications();
  notifications.add(run_id);
  save_notifications(notifications);
}

function unfollow_run(run_id) {
  let notifications = get_notifications();
  notifications.remove(run_id);
  save_notifications(notifications);
}

function following_run(run_id) {
  let notifications = get_notifications();
  return notifications.contains(run_id);
}

function set_follow_button(run_id) {
  let button = document.getElementById("follow_elo");
  let notifications = get_notifications();
  if (notifications.contains(run_id)) {
    button.textContent = "Unfollow";
  } else {
    button.textContent = "Follow";
  }
  button.style.display = "";
}

async function handle_follow_button(run_id) {
  await DOM_loaded();
  window.addEventListener("storage", (event) => {
    if (event.key == fishtest_notifications_key) {
      set_follow_button(run_id);
    }
  });
  let button = document.getElementById("follow_elo");
  button.onclick = () => {
    if (button.textContent.trim() == "Follow") {
      if (supportsNotifications() && Notification.permission === "default") {
        Notification.requestPermission();
      }
      follow_run(run_id);
    } else {
      unfollow_run(run_id);
    }
    set_follow_button(run_id);
  };
  set_follow_button(run_id);
}

main_follow_loop();
