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
        })

        const selectedTbodyId = e.target.dataset.handleTargetCustom;
        document.getElementById(selectedTbodyId).classList.remove("d-none");
        document.getElementById("users-table-toggle").textContent = e.target.textContent;
      })
    })
  }

  handleToggleUsers();

</script>

<h2>User Management</h2>

<div class="mw-xxl">
  <div class="row g-3 mb-3">
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center">
        <div class="card-header text-nowrap" title="All Users">All</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace">${len(all_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center">
        <div class="card-header text-nowrap" title="Pending Users">Pending</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace">${len(pending_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center">
        <div class="card-header text-nowrap" title="Blocked users">Blocked</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace">${len(blocked_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center">
        <div class="card-header text-nowrap" title="Idle Users">Idle</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace">${len(idle_users)}</h4>
        </div>
      </div>
    </div>
    <div class="col-6 col-sm">
      <div class="card card-lg-sm text-center">
        <div class="card-header text-nowrap" title="Approver Users">Approvers</div>
        <div class="card-body">
          <h4 class="card-title mb-0 monospace">${len(approvers_users)}</h4>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="users-table-handler" class="dropdown">
  <button
    id="users-table-toggle"
    class="btn btn-secondary dropdown-toggle"
    type="button"
    data-bs-toggle="dropdown"
    aria-expanded="false"
  >Pending</button>

  <ul class="dropdown-menu">
    <li><span class="dropdown-item" data-handle-target-custom="all-users">All</span></li>
    <li><span class="dropdown-item" data-handle-target-custom="pending-users">Pending</span></li>
    <li><span class="dropdown-item" data-handle-target-custom="blocked-users">Blocked</span></li>
    <li><span class="dropdown-item" data-handle-target-custom="idle-users">Idle</span></li>
    <li><span class="dropdown-item" data-handle-target-custom="approvers-users">Approvers</span></li>
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

  <tbody id="all-users" class="d-none">
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
          <td colspan=20>No users found</td>
        </tr>
      % endif
  </tbody>

  <tbody id="pending-users">
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
          <td colspan=20>No pending users</td>
        </tr>
      % endif
  </tbody>

  <tbody id="blocked-users" class="d-none">
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
        <td colspan=20>No blocked users</td>
      </tr>
    % endif
  </tbody>

  <tbody id="idle-users" class="d-none">
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
        <td colspan=20>No idle users</td>
      </tr>
    % endif
  </tbody>


  <tbody id="approvers-users" class="d-none">
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
          <td colspan=20>No approver users</td>
      </tr>
    % endif
  </tbody> 
</table>
