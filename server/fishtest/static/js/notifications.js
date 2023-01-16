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
  return {
    capacity: capacity,
    content: content,
    count() {
      return this.content.length;
    },
    copy() {
      return new LRU(this.capacity, this.content.slice());
    },
    add(elt) {
      if (this.contains(elt)) {
        return null;
      } else {
        this.content.push(elt);
        if (this.content.length > this.capacity) {
          const drop = this.content[0];
          this.content.shift();
          return drop;
        } else {
          return null;
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
const fishtest_timestamp_key = "fishtest_timestamp";

function notify_fishtest_(message) {
  const div = document.getElementById("fallback_div");
  const span = document.getElementById("fallback");
  const fallback_div = document.getElementById("fallback_div");
  if (fallback_div.style.display == "none") {
    span.innerHTML = message;
  } else {
    span.innerHTML += "<hr> " + message;
  }
  let count = span.innerHTML.split("<hr>").length;
  process_title(count);
  div.style.display = "block";
}

function notify_fishtest(message) {
  broadcast("notify_fishtest_", message);
}

function notify_elo(entry_start, entry_finished) {
  const tag = entry_finished["run"].slice(0, -8);
  const message_finished = entry_finished["message"];
  const username = entry_finished["username"];
  const color = message_finished.split(" ")[0].split(":")[1];
  const first_line_idx = message_finished.indexOf(" ") + 1;
  const first_line = message_finished.slice(first_line_idx);
  const title = `Test ${tag} by ${username} finished ${color}!`;
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
    const message = `<a href=${link}>${escapeHtml(title)} ${escapeHtml(
      body
    )}</a>`;
    notify_fishtest(message);
  });
}

const design_capacity = 15;

function get_notifications() {
  let notifications;
  try {
    notifications = LRU.load(fishtest_notifications_key);
    if (notifications["capacity"] != design_capacity) {
      throw "";
    }
    return notifications;
  } catch (e) {
    console.log("Initializing new LRU object");
    notifications = new LRU(design_capacity);
    notifications.save(fishtest_notifications_key);
    return notifications;
  }
}

function save_notifications(notifications) {
  notifications.save(fishtest_notifications_key);
}

function get_timestamp() {
  let ts;
  try {
    ts = JSON.parse(localStorage.getItem(fishtest_timestamp_key));
  } catch (e) {
    return null;
  }
  if (typeof ts != "number") {
    return null;
  }
  return ts;
}

function save_timestamp(ts) {
  localStorage.setItem(fishtest_timestamp_key, JSON.stringify(ts));
}

async function main_follow_loop() {
  await DOM_loaded();
  await async_sleep(10000);
  while (true) {
    const current_time = Date.now();
    const timestamp_latest_fetch = get_timestamp();
    if (
      timestamp_latest_fetch != null &&
      current_time - timestamp_latest_fetch < 19000
    ) {
      console.log("Skipping events update");
      await async_sleep(20000 + 500 * Math.random());
      continue;
    }
    let json;
    let notifications = get_notifications();
    try {
      json = await fetch_post("/api/actions", {
        action: "finished_run",
        run_id: { $in: notifications.content },
      });
    } catch (e) {
      console.log(e);
      await async_sleep(20000 + 500 * Math.random());
      continue;
    }
    save_timestamp(current_time);
    notifications = get_notifications();
    let work = [];
    json.forEach((entry) => {
      let run_id = entry["run_id"];
      if (notifications.contains(run_id)) {
        work.push(entry);
        notifications.remove(run_id);
      }
    });
    save_notifications(notifications); // make sure other tabs see up to date data
    // Instrumentation
    console.log("active notifications: ", JSON.stringify(notifications));
    work.forEach(async (entry) => {
      run_id = entry["run_id"];
      disable_notification(run_id);
      set_notification_status(run_id);
      let json;
      try {
        json = await fetch_post("/api/actions", {
          action: "new_run",
          run_id: run_id,
        });
        notify_elo(json[0], entry);
      } catch (e) {
        // TODO: try to deal with network errors
        console.log(e);
        notify_elo(null, entry);
      }
    });
    await async_sleep(20000 + 500 * Math.random());
  }
}

function follow_run(run_id) {
  let notifications = get_notifications();
  const ret = notifications.add(run_id);
  save_notifications(notifications);
  return ret;
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

function set_notification_status_(run_id) {
  let button = document.getElementById(`follow_button_${run_id}`);
  if (button) {
    if (following_run(run_id)) {
      button.textContent = "Unfollow";
    } else {
      button.textContent = "Follow";
    }
    button.style.display = "";
  }

  let notification_id = "notification_" + run_id;
  let notification = document.getElementById(notification_id);
  if (notification) {
    if (following_run(run_id)) {
      notification.title = "Click to unfollow: no notification";
      notification.innerHTML =
        "<div style='white-space:nowrap;'><i class='fa-regular fa-bell' style='width:20px;'></i><i class='fa-solid fa-toggle-on'></i></div>";
    } else {
      notification.title = "Click to follow: get notification";
      notification.innerHTML =
        "<div style='white-space:nowrap;'><i class='fa-regular fa-bell-slash' style='width:20px;'></i><i class='fa-solid fa-toggle-off'></i></div>";
    }
  }
}

function set_notification_status(run_id) {
  broadcast("set_notification_status_", run_id);
}

function toggle_notifaction_status(run_id) {
  if (!following_run(run_id)) {
    if (supportsNotifications() && Notification.permission === "default") {
      Notification.requestPermission();
    }
    const drop = follow_run(run_id);
    if (drop) {
      set_notification_status(drop);
    }
  } else {
    unfollow_run(run_id);
  }
  set_notification_status(run_id);
}

// old style callback on main page: onclick="handle_notification(this)"
function handle_notification(notification) {
  run_id = notification.id.split("_")[1];
  toggle_notifaction_status(run_id);
}

// old style callback on tests_view page
function handle_follow_button(button) {
  run_id = button.id.split("_")[2];
  toggle_notifaction_status(run_id);
}

function disable_notification_(run_id) {
  let button = document.getElementById(`follow_button_${run_id}`);
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

main_follow_loop();
