function LRU(capacity, content) {
  if (!content) {
    content = [];
  }
  if (typeof capacity != "number") {
    throw "capacity is not a number";
  }
  if (!(content instanceof Array)) {
    throw "content is not an Array";
  }
  if (content.length != 0 && !(content[0] instanceof Array)) {
    throw "content entry has the wrong type";
  }
  return {
    capacity: capacity,
    content: content,
    count() {
      return this.content.length;
    },
    copy() {
      return new LRU(this.capacity, JSON.parse(JSON.stringify(this.content)));
    },
    toArray() {
      let ret = [];
      for (const elt of this.content) {
        ret.push(elt[0]);
      }
      return ret;
    },
    isEqual(elt) {
      return JSON.stringify(this) == JSON.stringify(elt);
    },
    toString() {
      elt = this.copy();
      for (const entry of elt.content) {
        const ts = entry[1];
        entry[1] = new Date(ts).toISOString();
      }
      return JSON.stringify(elt.content);
    },
    add(elt) {
      if (this.contains(elt)) {
        return null;
      } else {
        this.content.push([elt, Date.now()]);
        if (this.content.length > this.capacity) {
          const drop = this.content[0];
          this.content.shift();
          return drop[0];
        } else {
          return null;
        }
      }
    },
    contains(elt) {
      return this.content.findIndex((x) => x[0] == elt) != -1;
    },
    timestamp(elt) {
      const idx = this.content.findIndex((x) => x[0] == elt);
      if (idx == -1) {
        return -1;
      } else {
        return this.content[idx][1];
      }
    },
    save(name) {
      save_object(name, this);
    },
    remove(elt, timestamp) {
      const idx = this.content.findIndex((x) => x[0] == elt);
      if (idx == -1) {
        return false;
      } else {
        if (timestamp && timestamp != this.content[idx][1]) {
          return false;
        }
        this.content.splice(idx, 1);
        return true;
      }
    },
  };
}

LRU.load = function (name) {
  const json = load_object(name);
  return new LRU(json["capacity"], json["content"]);
};

const fishtest_follow_lock = "fishtest_follow_lock";

function has_web_locks() {
  if (navigator.locks) {
    return true;
  }
  return false;
}

function notify_fishtest_(message) {
  const div = document.getElementById("fallback_div");
  const span = document.getElementById("fallback");
  const fallback_div = document.getElementById("fallback_div");
  if (fallback_div.style.display == "none") {
    span.replaceChildren();
    span.insertAdjacentHTML("beforeend", message);
  } else {
    span.insertAdjacentHTML("beforeend", "<hr>");
    span.insertAdjacentHTML("beforeend", message);
  }
  const count = span.querySelectorAll(".notification-message").length;
  process_title(count);
  div.style.display = "block";
}

function notify_fishtest(message) {
  broadcast("notify_fishtest_", message);
}

function notify_elo(entry_start, entry_finished) {
  // Currently entry_start may be null because of
  // network errors.
  const tag = entry_finished["run"].slice(0, -8);
  let username = "unknown";
  if (entry_start) {
    username = entry_start["username"];
  } else if (entry_finished["action"] === "finished_run") {
    // For stopped and deleted runs the username refers
    // to the user that did the stopping/deleting.
    // This is not what we want.
    username = entry_finished["username"];
  }
  let first_line = "";
  let state = "";
  if (entry_finished["action"] === "finished_run") {
    const message_finished = entry_finished["message"];
    state = message_finished.split(" ")[0].split(":")[1];
    const first_line_idx = message_finished.indexOf(" ") + 1;
    first_line = message_finished.slice(first_line_idx);
  } else if (entry_finished["action"] == "delete_run") {
    state = "deleted";
  } else if (entry_finished["action"] == "stop_run") {
    state = "stopped";
  }
  const title = state
    ? `Test ${tag} by ${username} was ${state}!`
    : `Test ${tag} by ${username}.`;
  let second_line;
  if (entry_start) {
    const message_start = entry_start["message"];
    second_line = ` *Testdata* ${message_start}`;
  } else {
    second_line = "";
  }
  const body = first_line + second_line;
  const link = `/tests/view/${entry_finished["run_id"]}`;
  notify(title, body, link, (title, body, link) => {
    const message = `<a class="notification-message" href=${link}>${escapeHtml(
      title,
    )} ${escapeHtml(body)}</a>`;
    notify_fishtest(message);
  });
}

const design_capacity = 15;

function get_notifications() {
  let notifications;
  try {
    notifications = LRU.load("notifications");
    if (notifications["capacity"] != design_capacity) {
      throw "Incompatible LRU object found";
    }
    return notifications;
  } catch (e) {
    console_log("Initializing new LRU object");
    notifications = new LRU(design_capacity);
    notifications.save("notifications");
    return notifications;
  }
}

function save_notifications(notifications) {
  notifications.save("notifications");
}

async function purge_notifications(last_fetch_time) {
  // Instrumentation
  console_log("Purging stale notifications.");
  let notifications = get_notifications();
  let json = {};
  try {
    json = await fetch_json("/api/active_runs");
  } catch (e) {
    console_log(e, true);
    return;
  }
  let work = [];
  for (const entry of notifications.content) {
    const run_id = entry[0];
    // If the run is not finished: keep.
    if (run_id in json) {
      continue;
    }
    // If there was recent activity: keep.
    // It will be dealt with in the normal way.
    let json1 = [];
    try {
      json1 = await fetch_post("/api/actions", {
        action: {
          $in: ["finished_run", "stop_run", "delete_run"],
        },
        run_id: run_id,
        time: { $gte: last_fetch_time / 1000 - 60 },
      });
    } catch (e) {
      console_log(e, true);
      return;
    }
    if (json1.length > 0) {
      continue;
    }
    work.push(entry);
  }
  for (const entry of work) {
    const run_id = entry[0];
    const timestamp = entry[1];
    await unfollow_run(run_id, timestamp);
  }
}

async function main_follow_loop() {
  await DOM_loaded();
  if (has_web_locks()) {
    console_log("Web locks supported!");
  } else {
    console_log("Web locks not supported!");
  }
  await async_sleep(5000 + 10000 * Math.random());
  let last_notifications = null;
  while (true) {
    let notifications = get_notifications();
    if (!notifications.isEqual(last_notifications)) {
      last_notifications = notifications;
      // Instrumentation
      console_log(`Active notifications: ${notifications}`);
    }
    const current_time = Date.now();
    const current_time_sig = `${current_time}_${Math.random()}`;
    const latest_fetch_time = load_object("latest_fetch_time");
    if (
      typeof latest_fetch_time == "number" &&
      current_time - latest_fetch_time < 19000
    ) {
      // Note that in modern browsers timer events in
      // inactive tabs are severely throttled.
      // So the actual delay may be longer than expected.
      await async_sleep(20000 + 500 * Math.random());
      continue;
    }
    // I won the race, other tabs should skip their fetch
    save_object("latest_fetch_time", current_time);
    save_object("latest_fetch_time_sig", current_time_sig);
    // Extra defense against race after wake up from sleep
    const t = await async_sleep(1500);
    if (t > 90000) {
      // Wake up from sleep: reset state
      continue;
    }
    if (current_time_sig != load_object("latest_fetch_time_sig")) {
      // My fetch was preempted by another tab
      continue;
    }
    let json = [];
    notifications = get_notifications();
    try {
      if (notifications.count()) {
        json = await fetch_post("/api/actions", {
          action: { $in: ["finished_run", "stop_run", "delete_run"] },
          run_id: { $in: notifications.toArray() },
        });
      }
    } catch (e) {
      console_log(e, true);
      continue;
    }
    notifications = get_notifications();
    let work = [];
    for (const entry of json) {
      const run_id = entry["run_id"];
      const ts = notifications.timestamp(run_id);
      // ignore events that happened before subscribing
      if (ts != -1 && entry["time"] >= ts / 1000) {
        if (await unfollow_run(run_id)) {
          work.push(entry);
        }
      }
    }
    for (const entry of work) {
      const run_id = entry["run_id"];
      disable_notification(run_id);
      set_notification_status(run_id);
      let json = [];
      try {
        json = await fetch_post("/api/actions", {
          action: "new_run",
          run_id: run_id,
        });
        notify_elo(json[0], entry);
      } catch (e) {
        // TODO: try to deal with network errors
        console_log(e, true);
        notify_elo(null, entry);
      }
    }
    const latest_purge_time = load_object("latest_purge_time");
    if (
      typeof latest_purge_time != "number" ||
      current_time - latest_purge_time > 20 * 1000 * 1000
    ) {
      save_object("latest_purge_time", current_time);
      // Note that because of sleeping, current_time may be long ago.
      // This is intentional!
      await purge_notifications(current_time);
    }
  }
}

function follow_run_(run_id) {
  const notifications = get_notifications();
  const ret = notifications.add(run_id);
  save_notifications(notifications);
  return ret;
}

async function follow_run(run_id) {
  if (navigator.locks) {
    return navigator.locks.request(fishtest_follow_lock, async (lock) => {
      return follow_run_(run_id);
    });
  } else {
    return follow_run_(run_id);
  }
}

function unfollow_run_(run_id, timestamp) {
  const notifications = get_notifications();
  const ret = notifications.remove(run_id, timestamp);
  if (ret) {
    save_notifications(notifications);
  }
  return ret;
}

async function unfollow_run(run_id, timestamp) {
  if (navigator.locks) {
    return navigator.locks.request(fishtest_follow_lock, async (lock) => {
      return unfollow_run_(run_id, timestamp);
    });
  } else {
    return unfollow_run_(run_id, timestamp);
  }
}

function following_run(run_id) {
  const notifications = get_notifications();
  return notifications.contains(run_id);
}

function set_notification_status_(run_id) {
  const button = document.getElementById(`follow_button_${run_id}`);
  if (button) {
    if (following_run(run_id)) {
      button.textContent = "Unfollow";
    } else {
      button.textContent = "Follow";
    }
    button.style.display = "";
  }

  const notification_id = "notification_" + run_id;
  const notification = document.getElementById(notification_id);
  if (notification) {
    if (following_run(run_id)) {
      notification.title = "Click to unfollow: no notification";

      const italic1 = document.createElement("i");
      italic1.className = "fa-regular fa-bell";
      italic1.style.width = "20px";

      const italic2 = document.createElement("i");
      italic2.className = "fa-solid fa-toggle-on";

      const notification_body = document.createElement("div");
      notification_body.style.whiteSpace = "nowrap";
      notification_body.append(italic1);
      notification_body.append(italic2);

      notification.replaceChildren();
      notification.append(notification_body);
    } else {
      notification.title = "Click to follow: get notification";

      const italic1 = document.createElement("i");
      italic1.className = "fa-regular fa-bell-slash";
      italic1.style.width = "20px";

      const italic2 = document.createElement("i");
      italic2.className = "fa-solid fa-toggle-off";

      const notification_body = document.createElement("div");
      notification_body.style.whiteSpace = "nowrap";
      notification_body.append(italic1);
      notification_body.append(italic2);

      notification.replaceChildren();
      notification.append(notification_body);
    }
  }
}

function set_notification_status(run_id) {
  broadcast("set_notification_status_", run_id);
}

async function toggle_notifaction_status(run_id) {
  if (!following_run(run_id)) {
    if (supportsNotifications() && Notification.permission === "default") {
      Notification.requestPermission();
    }
    const drop = await follow_run(run_id);
    if (drop) {
      set_notification_status(drop);
    }
  } else {
    await unfollow_run(run_id);
  }
  set_notification_status(run_id);
}

// old style callback on main page: onclick="handle_notification(this)"
async function handle_notification(notification) {
  const run_id = notification.id.split("_")[1];
  await toggle_notifaction_status(run_id);
}

// old style callback on tests_view page
async function handle_follow_button(button) {
  const run_id = button.id.split("_")[2];
  await toggle_notifaction_status(run_id);
}

// old style callback
async function handle_stop_delete_button(run_id) {
  await unfollow_run(run_id);
  disable_notification(run_id);
}

// new style callback
function dismiss_notification(elt_id) {
  broadcast("dismiss_notification_", elt_id);
}

function dismiss_notification_(elt_id) {
  const elt = document.getElementById(elt_id);
  elt.style.display = "none";
  // remove message count from the title
  process_title(0);
}

function disable_notification_(run_id) {
  const button = document.getElementById(`follow_button_${run_id}`);
  if (button) {
    button.disabled = 1;
  }

  let notification_id = "notification_" + run_id;
  let notification = document.getElementById(notification_id);
  if (notification) {
    notification.style.opacity = 0.5;
    notification.style["pointer-events"] = "none";
  }
}

function disable_notification(run_id) {
  broadcast("disable_notification_", run_id);
}

broadcast_dispatch["notify_fishtest_"] = notify_fishtest_;
broadcast_dispatch["set_notification_status_"] = set_notification_status_;
broadcast_dispatch["disable_notification_"] = disable_notification_;
broadcast_dispatch["dismiss_notification_"] = dismiss_notification_;

function cleanup_() {
  // Remove stale local storage items.
  localStorage.removeItem("fishtest_disable_notification");
  localStorage.removeItem("fishtest_notifications");
  localStorage.removeItem("fishtest_notifications_v2");
  localStorage.removeItem("fishtest_timestamp");
  localStorage.removeItem("fishtest_timestamp_purge");
}

cleanup_();
main_follow_loop();
