<%
  # to differentiate toggle states on different pages
  import binascii
  prefix = 'user'+binascii.hexlify(username.encode()).decode()+"_" if username is not Undefined else ""
%>

<script>
  function set_notification(run_id) {
    let notification_id = "notification_"+run_id;
    let notification = document.getElementById(notification_id);
    if(following_run(run_id)){
      notification.title = "Click to unfollow: no notification";
      notification.innerHTML = "<div style='white-space:nowrap;'><i class='fa-regular fa-bell' style='padding:0px 2px;'></i><i class='fa-solid fa-toggle-on'></i></div>";

    } else {
      notification.title = "Click to follow: get notification";
      notification.innerHTML = "<div style='white-space:nowrap;'><i class='fa-regular fa-bell-slash'></i><i class='fa-solid fa-toggle-off'></i></div>";
    }
  }

  function handle_notification(notification) {
    console.log("in handle_notification");
    run_id = notification.id.split("_")[1];
    if(!following_run(run_id)){
      if (supportsNotifications() && Notification.permission === "default") {
        Notification.requestPermission();
      }
      follow_run(run_id);
    } else {
      unfollow_run(run_id);
    }
    set_notification(run_id);
  }
  
  window.addEventListener("storage", (event) => {
    if (event.key == fishtest_notifications_key) {
      let all_notifications = document.querySelectorAll(".notifications");
      all_notifications.forEach((notification) => {
        run_id = notification.id.split("_")[1];
        set_notification(run_id);
      });
    }
  });
</script>


% if page_idx == 0:
    <% pending_approval_runs = [run for run in runs['pending'] if not run['approved']] %>
    <% paused_runs = [run for run in runs['pending'] if run['approved']] %>

    <%include file="run_table.mak" args="runs=pending_approval_runs,
                                         show_delete=True,
                                         header='Pending approval',
                                         count=len(pending_approval_runs),
                                         toggle=prefix+'pending',
                                         alt='No tests pending approval'"
    />


    <%include file="run_table.mak" args="runs=paused_runs,
                                         show_delete=True,
                                         header='Paused',
                                         count=len(paused_runs),
                                         toggle=prefix+'paused',
                                         alt='No paused tests'"
     />

    <%include file="run_table.mak" args="runs=failed_runs,
                                         show_delete=True,
                                         toggle=prefix+'failed',
                                         count=len(failed_runs),
                                         header='Failed',
                                         alt='No failed tests on this page'"
    />

    <%include file="run_table.mak" args="runs=runs['active'],
                                         header='Active',
                                         toggle=prefix+'active',
                                         count=len(runs['active']),
                                         alt='No active tests'"
    />

% endif

<%include file="run_table.mak" args="runs=finished_runs,
                                     header='Finished',
                                     count=num_finished_runs,
                                     toggle=prefix+'finished' if page_idx==0 else None,
                                     pages=finished_runs_pages"
/>
