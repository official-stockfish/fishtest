<%inherit file="base.mak"/>

<%!
  from fishtest.util import delta_date, diff_date, format_group
%>

<script>
  document.title = "User Management | Stockfish Testing";
  async function handleToggleUsers() {
    await DOMContentLoaded();
    const tableHandlers =
      [...document.getElementById("users-table-handler").querySelectorAll(".dropdown-item")];
    tableHandlers.forEach((tableHandler) => {
      tableHandler.addEventListener("click", (e) => {
        const tableBodies =
          [...document.getElementById("users-table").querySelectorAll("tbody")];

        tableBodies.forEach((tableBody) => {
          tableBody.classList.add("d-none");
          tableBody.setAttribute("aria-hidden", "true");
        });

        const selectedTbodyId = e.target.dataset.handleTargetCustom;
        const selectedTbody = document.getElementById(selectedTbodyId);
        selectedTbody.classList.remove("d-none");
        selectedTbody.removeAttribute("aria-hidden");
        document.getElementById("users-table-toggle").textContent = e.target.textContent;
      });
    });
  }

  handleToggleUsers();

</script>

<h2>User Management</h2>

<div class="mw-xxl">
  <div class="row g-3 mb-3">
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center" role="region" aria-labelledby="all-users-header">
        <div class="card-header text-nowrap" id="all-users-header" title="All Users">All</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace" aria-live="polite">${len(all_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center" role="region" aria-labelledby="pending-users-header">
        <div class="card-header text-nowrap" id="pending-users-header" title="Pending Users">Pending</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace" aria-live="polite">${len(pending_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center" role="region" aria-labelledby="blocked-users-header">
        <div class="card-header text-nowrap" id="blocked-users-header" title="Blocked Users">Blocked</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace" aria-live="polite">${len(blocked_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center" role="region" aria-labelledby="idle-users-header">
        <div class="card-header text-nowrap" id="idle-users-header" title="Idle Users">Idle</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace" aria-live="polite">${len(idle_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center" role="region" aria-labelledby="approvers-users-header">
        <div class="card-header text-nowrap" id="approvers-users-header" title="Approver Users">Approvers</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace" aria-live="polite">${len(approvers_users)}</h4>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="users-table-handler" class="dropdown" role="navigation" aria-label="User table category selection">
  <button
    id="users-table-toggle"
    class="btn btn-secondary dropdown-toggle"
    type="button"
    data-bs-toggle="dropdown"
    aria-expanded="false"
    aria-haspopup="menu"
  >Pending</button>

  <ul class="dropdown-menu" aria-labelledby="users-table-toggle" role="menu">
    <li role="menuitem"><span class="dropdown-item" data-handle-target-custom="all-users" tabindex="0">All</span></li>
    <li role="menuitem"><span class="dropdown-item" data-handle-target-custom="pending-users" tabindex="0">Pending</span></li>
    <li role="menuitem"><span class="dropdown-item" data-handle-target-custom="blocked-users" tabindex="0">Blocked</span></li>
    <li role="menuitem"><span class="dropdown-item" data-handle-target-custom="idle-users" tabindex="0">Idle</span></li>
    <li role="menuitem"><span class="dropdown-item" data-handle-target-custom="approvers-users" tabindex="0">Approvers</span></li>
  </ul>
</div>

<table id="users-table" class="table table-striped table-sm">
  <thead>
    <tr>
      <th style="width:20%">Username</th>
      <th style="width:20%">Registration Time</th>
      <th style="width:20%">Groups</th>
      <th style="width:40%">Email</th>
    </tr>
  </thead>

  <tbody id="all-users" class="d-none" aria-hidden="true">
    % for user in all_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:20%">${format_group(user['groups'])}</td>
        <td style="width:40%">${user['email']}</td>
      </tr>
    % endfor
    % if len(all_users) == 0:
      <tr>
        <td colspan="4">No users found</td>
      </tr>
    % endif
  </tbody>

  <tbody id="pending-users" aria-hidden="false">
    % for user in pending_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:20%">${format_group(user['groups'])}</td>
        <td style="width:40%">${user['email']}</td>
      </tr>
    % endfor
    % if len(pending_users) == 0:
      <tr>
        <td colspan="4">No pending users</td>
      </tr>
    % endif
  </tbody>

  <tbody id="blocked-users" class="d-none" aria-hidden="true">
    % for user in blocked_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:20%">${format_group(user['groups'])}</td>
        <td style="width:40%">${user['email']}</td>
      </tr>
    % endfor
    % if len(blocked_users) == 0:
      <tr>
        <td colspan="4">No blocked users</td>
      </tr>
    % endif
  </tbody>

  <tbody id="idle-users" class="d-none" aria-hidden="true">
    % for user in idle_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:20%">${format_group(user['groups'])}</td>
        <td style="width:40%">${user['email']}</td>
      </tr>
    % endfor
    % if len(idle_users) == 0:
      <tr>
        <td colspan="4">No idle users</td>
      </tr>
    % endif
  </tbody>

  <tbody id="approvers-users" class="d-none" aria-hidden="true">
    % for user in approvers_users:
      <tr>
        <td style="width:20%"><a href="/user/${user['username']}">${user['username']}</a></td>
        <td style="width:20%">${user['registration_time'].strftime("%y-%m-%d %H:%M:%S") if 'registration_time' in user else 'Unknown'}</td>
        <td style="width:20%">${format_group(user['groups'])}</td>
        <td style="width:40%">${user['email']}</td>
      </tr>
    % endfor
    % if len(approvers_users) == 0:
      <tr>
        <td colspan="4">No approver users</td>
      </tr>
    % endif
  </tbody>
</table>
