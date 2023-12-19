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
      for (const el of this.content) {
        ret.push(el[0]);
      }
      return ret;
    },
    isEqual(el) {
      return JSON.stringify(this) === JSON.stringify(el);
    },
    toString() {
      el = this.copy();
      for (const entry of el.content) {
        const ts = entry[1];
        entry[1] = new Date(ts).toISOString();
      }
      return JSON.stringify(el.content);
    },
    add(el) {
      if (this.contains(el)) {
        return null;
      } else {
        this.content.push([el, Date.now()]);
        if (this.content.length > this.capacity) {
          const drop = this.content[0];
          this.content.shift();
          return drop[0];
        } else {
          return null;
        }
      }
    },
    contains(el) {
      return this.content.findIndex((x) => x[0] === el) != -1;
    },
    timestamp(el) {
      const idx = this.content.findIndex((x) => x[0] === el);
      if (idx === -1) {
        return -1;
      } else {
        return this.content[idx][1];
      }
    },
    save(name) {
      saveObject(name, this);
    },
    remove(el, timestamp) {
      const idx = this.content.findIndex((x) => x[0] === el);
      if (idx === -1) {
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
  const json = loadObject(name);
  return new LRU(json["capacity"], json["content"]);
};

const fishtestFollowLock = "fishtest_follow_lock";

function hasWebLocks() {
  if (navigator.locks) {
    return true;
  }
  return false;
}

function notifyFishtest_(message) {
  const div = document.getElementById("fallback_div");
  const span = document.getElementById("fallback");
  const fallback_div = document.getElementById("fallback_div");
  if (fallback_div.style.display === "none") {
    span.replaceChildren();
    span.insertAdjacentHTML("beforeend", message);
  } else {
    span.insertAdjacentHTML("beforeend", "<hr>");
    span.insertAdjacentHTML("beforeend", message);
  }
  const count = span.querySelectorAll(".notification-message").length;
  handleTitle(count);
  div.style.display = "block";
}

function notifyFishtest(message) {
  broadcast("notifyFishtest_", message);
}

function notifyElo(entryStart, entryFinished) {
  // Currently entryStart may be null because of
  // network errors.
  const tag = entryFinished["run"].slice(0, -8);
  let username = "unknown";
  if (entryStart) {
    username = entryStart["username"];
  } else if (entryFinished["action"] === "finished_run") {
    // For stopped and deleted runs the username refers
    // to the user that did the stopping/deleting.
    // This is not what we want.
    username = entryFinished["username"];
  }
  let firstLine = "";
  let state = "";
  if (entryFinished["action"] === "finished_run") {
    const messageFinished = entryFinished["message"];
    state = messageFinished.split(" ")[0].split(":")[1];
    const firstLineIdx = messageFinished.indexOf(" ") + 1;
    firstLine = messageFinished.slice(firstLineIdx);
  } else if (entryFinished["action"] === "delete_run") {
    state = "deleted";
  } else if (entryFinished["action"] === "stop_run") {
    state = "stopped";
  }
  const title = state
    ? `Test ${tag} by ${username} was ${state}!`
    : `Test ${tag} by ${username}.`;
  let secondLine;
  if (entryStart) {
    const messageStart = entryStart["message"];
    secondLine = ` *Testdata* ${messageStart}`;
  } else {
    secondLine = "";
  }
  const body = firstLine + secondLine;
  const link = `/tests/view/${entryFinished["run_id"]}`;
  notify(title, body, link, (title, body, link) => {
    const message = `<a class="notification-message" href=${link}>${escapeHtml(
      title,
    )} ${escapeHtml(body)}</a>`;
    notifyFishtest(message);
  });
}

const designCapacity = 15;

function getNotifications() {
  let notifications;
  try {
    notifications = LRU.load("notifications");
    if (notifications["capacity"] != designCapacity) {
      throw "Incompatible LRU object found";
    }
    return notifications;
  } catch (e) {
    log("Initializing new LRU object");
    notifications = new LRU(designCapacity);
    notifications.save("notifications");
    return notifications;
  }
}

function saveNotifications(notifications) {
  notifications.save("notifications");
}

async function purgeNotifications(lastFetchTime) {
  // Instrumentation
  log("Purging stale notifications.");
  let notifications = getNotifications();
  let json = {};
  try {
    json = await fetchJson("/api/active_runs");
  } catch (e) {
    log(e, true);
    return;
  }
  let work = [];
  for (const entry of notifications.content) {
    const runId = entry[0];
    // If the run is not finished: keep.
    if (runId in json) {
      continue;
    }
    // If there was recent activity: keep.
    // It will be dealt with in the normal way.
    let json1 = [];
    try {
      json1 = await fetchPost("/api/actions", {
        action: {
          $in: ["finished_run", "stop_run", "delete_run"],
        },
        run_id: runId,
        time: { $gte: lastFetchTime / 1000 - 60 },
      });
    } catch (e) {
      log(e, true);
      return;
    }
    if (json1.length > 0) {
      continue;
    }
    work.push(entry);
  }
  for (const entry of work) {
    const runId = entry[0];
    const timestamp = entry[1];
    await unfollowRun(runId, timestamp);
  }
}

async function mainFollowLoop() {
  await DOMContentLoaded();
  if (hasWebLocks()) {
    log("Web locks supported!");
  } else {
    log("Web locks not supported!");
  }
  await asyncSleep(5000 + 10000 * Math.random());
  let lastNotifications = null;
  while (true) {
    let notifications = getNotifications();
    if (!notifications.isEqual(lastNotifications)) {
      lastNotifications = notifications;
      // Instrumentation
      log(`Active notifications: ${notifications}`);
    }
    const currentTime = Date.now();
    const currentTimeSig = `${currentTime}_${Math.random()}`;
    const latestFetchTime = loadObject("latestFetchTime");
    if (
      typeof latestFetchTime === "number" &&
      currentTime - latestFetchTime < 19000
    ) {
      // Note that in modern browsers timer events in
      // inactive tabs are severely throttled.
      // So the actual delay may be longer than expected.
      await asyncSleep(20000 + 500 * Math.random());
      continue;
    }
    // I won the race, other tabs should skip their fetch
    saveObject("latestFetchTime", currentTime);
    saveObject("latestFetchTimeSig", currentTimeSig);
    // Extra defense against race after wake up from sleep
    const t = await asyncSleep(1500);
    if (t > 90000) {
      // Wake up from sleep: reset state
      continue;
    }
    if (currentTimeSig != loadObject("latestFetchTimeSig")) {
      // My fetch was preempted by another tab
      continue;
    }
    let json = [];
    notifications = getNotifications();
    try {
      if (notifications.count()) {
        json = await fetchPost("/api/actions", {
          action: { $in: ["finished_run", "stop_run", "delete_run"] },
          run_id: { $in: notifications.toArray() },
        });
      }
    } catch (e) {
      log(e, true);
      continue;
    }
    notifications = getNotifications();
    let work = [];
    for (const entry of json) {
      const runId = entry["run_id"];
      const ts = notifications.timestamp(runId);
      // ignore events that happened before subscribing
      if (ts != -1 && entry["time"] >= ts / 1000) {
        if (await unfollowRun(runId)) {
          work.push(entry);
        }
      }
    }
    for (const entry of work) {
      const runId = entry["run_id"];
      disableNotification(runId);
      setNotificationStatus(runId);
      let json = [];
      try {
        json = await fetchPost("/api/actions", {
          action: "new_run",
          run_id: runId,
        });
        notifyElo(json[0], entry);
      } catch (e) {
        // TODO: try to deal with network errors
        log(e, true);
        notifyElo(null, entry);
      }
    }
    const latestPurgeTime = loadObject("latestPurgeTime");
    if (
      typeof latestPurgeTime != "number" ||
      currentTime - latestPurgeTime > 20 * 1000 * 1000
    ) {
      saveObject("latestPurgeTime", currentTime);
      // Note that because of sleeping, currentTime may be long ago.
      // This is intentional!
      await purgeNotifications(currentTime);
    }
  }
}

function followRun_(runId) {
  const notifications = getNotifications();
  const ret = notifications.add(runId);
  saveNotifications(notifications);
  return ret;
}

async function followRun(runId) {
  if (navigator.locks) {
    return navigator.locks.request(fishtestFollowLock, async (lock) => {
      return followRun_(runId);
    });
  } else {
    return followRun_(runId);
  }
}

function unfollowRun_(runId, timestamp) {
  const notifications = getNotifications();
  const ret = notifications.remove(runId, timestamp);
  if (ret) {
    saveNotifications(notifications);
  }
  return ret;
}

async function unfollowRun(runId, timestamp) {
  if (navigator.locks) {
    return navigator.locks.request(fishtestFollowLock, async (lock) => {
      return unfollowRun_(runId, timestamp);
    });
  } else {
    return unfollowRun_(runId, timestamp);
  }
}

function followingRun(runId) {
  const notifications = getNotifications();
  return notifications.contains(runId);
}

function setNotificationStatus_(runId) {
  const button = document.getElementById(`follow_button_${runId}`);
  if (button) {
    if (followingRun(runId)) {
      button.textContent = "Unfollow";
    } else {
      button.textContent = "Follow";
    }
    button.style.display = "";
  }

  const notificationId = "notification_" + runId;
  const notification = document.getElementById(notificationId);
  if (notification) {
    if (followingRun(runId)) {
      notification.title = "Click to unfollow: no notification";

      const italic1 = document.createElement("i");
      italic1.className = "fa-regular fa-bell";
      italic1.style.width = "20px";

      const italic2 = document.createElement("i");
      italic2.className = "fa-solid fa-toggle-on";

      const notificationBody = document.createElement("div");
      notificationBody.style.whiteSpace = "nowrap";
      notificationBody.append(italic1);
      notificationBody.append(italic2);

      notification.replaceChildren();
      notification.append(notificationBody);
    } else {
      notification.title = "Click to follow: get notification";

      const italic1 = document.createElement("i");
      italic1.className = "fa-regular fa-bell-slash";
      italic1.style.width = "20px";

      const italic2 = document.createElement("i");
      italic2.className = "fa-solid fa-toggle-off";

      const notificationBody = document.createElement("div");
      notificationBody.style.whiteSpace = "nowrap";
      notificationBody.append(italic1);
      notificationBody.append(italic2);

      notification.replaceChildren();
      notification.append(notificationBody);
    }
  }
}

function setNotificationStatus(runId) {
  broadcast("setNotificationStatus_", runId);
}

async function toggleNotifactionStatus(runId) {
  if (!followingRun(runId)) {
    if (supportsNotifications() && Notification.permission === "default") {
      Notification.requestPermission();
    }
    const drop = await followRun(runId);
    if (drop) {
      setNotificationStatus(drop);
    }
  } else {
    await unfollowRun(runId);
  }
  setNotificationStatus(runId);
}

// old style callback on main page: onclick="handleNotification(this)"
async function handleNotification(notification) {
  const runId = notification.id.split("_")[1];
  await toggleNotifactionStatus(runId);
}

// old style callback on tests_view page
async function handleFollowButton(button) {
  const runId = button.id.split("_")[2];
  await toggleNotifactionStatus(runId);
}

// old style callback
async function handleStopDeleteButton(runId) {
  await unfollowRun(runId);
  disableNotification(runId);
}

// new style callback
function dismissNotification(elId) {
  broadcast("dismissNotification_", elId);
}

function dismissNotification_(elId) {
  const el = document.getElementById(elId);
  el.style.display = "none";
  // remove message count from the titlenotificationBody
  handleTitle(0);
}

function disableNotification_(runId) {
  const button = document.getElementById(`follow_button_${runId}`);
  if (button) {
    button.disabled = 1;
  }

  let notificationId = "notification_" + runId;
  let notification = document.getElementById(notificationId);
  if (notification) {
    notification.style.opacity = 0.5;
    notification.style["pointer-events"] = "none";
  }
}

function disableNotification(runId) {
  broadcast("disableNotification_", runId);
}

broadcastDispatch["notifyFishtest_"] = notifyFishtest_;
broadcastDispatch["setNotificationStatus_"] = setNotificationStatus_;
broadcastDispatch["disableNotification_"] = disableNotification_;
broadcastDispatch["dismissNotification_"] = dismissNotification_;

function cleanup_() {
  // Remove stale local storage items.
  localStorage.removeItem("fishtest_disable_notification");
  localStorage.removeItem("fishtest_notifications");
  localStorage.removeItem("fishtest_notifications_v2");
  localStorage.removeItem("fishtest_timestamp");
  localStorage.removeItem("fishtest_timestamp_purge");
  localStorage.removeItem("__fishtest__latest_purge_time");
  localStorage.removeItem("__fishtest__latest_fetch_time_sig");
  localStorage.removeItem("__fishtest__latest_fetch_time");
}

cleanup_();
mainFollowLoop();
