<%inherit file="base.mak"/>

<script>
  document.title = "User Management | Stockfish Testing";
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>User Management</h2>
    <div class="alert alert-info">
      <h4 class="alert-heading">
        <a href="/tests/user/${user['username']}" class="alert-link col-6 text-break">${user['username']}</a>
      </h4>
      <div class="row g-1">
        % if not profile:
          <div class="col-6 text-md-end">Email:</div>
          <div class="col-6 text-start text-break">
            <a href="mailto:${user['email']}?Subject=Fishtest%20Account" class="alert-link">
              ${user['email']}
            </a>
          </div>
        % endif
        <div class="col-6 text-md-end">Registered:</div>
        <div class="col-6 text-start text-break">
          ${user['registration_time'] if 'registration_time' in user else 'Unknown'}
        </div>
        <div class="col-6 text-md-end">Machine Limit:</div>
        <div class="col-6 text-start text-break">${limit}</div>
        <div class="col-6 text-md-end">CPU-Hours:</div>
        <div class="col-6 text-start text-break">${hours}</div>
      </div>
    </div>
  </header>

  <form action="${request.url}" method="POST">
    <input
      type="hidden"
      name="user"
      value="${user['username']}"
    >
    % if profile:
      <div class="form-floating mb-3">
        <input
          type="email"
          class="form-control mb-3"
          id="email"
          name="email"
          value="${user['email']}"
          placeholder="Email"
          required
        />
        <label for="email" class="d-flex align-items-end">Email</label>
      </div>

      <div class="input-group mb-3">
        <div class="form-floating">
          <input
            type="password"
            class="form-control"
            id="password"
            name="password"
            placeholder="Password"
            pattern=".{8,}"
            title="Eight or more characters: a password too simple or trivial to guess will be rejected"
            required
          />
          <label for="password" class="d-flex align-items-end">New Password</label>
        </div>
        <span class="input-group-text toggle-password-visibility" role="button">
          <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
        </span>
      </div>

      <div class="input-group mb-3">
        <div class="form-floating">
          <input
            type="password"
            class="form-control"
            id="password2"
            name="password2"
            placeholder="Repeat Password"
            required
          />
          <label for="password2" class="d-flex align-items-end">Repeat Password</label>
        </div>
        <span class="input-group-text toggle-password-visibility" role="button">
          <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
        </span>
      </div>
    <button type="submit" class="btn btn-primary w-100">Submit</button>
    % elif 'pending' in user and user['pending']:
      <div class="alert alert-dark mb-3">
        <label class="mb-2 h5">User Approval:</label>
        <div class="w-100 d-flex justify-content-between">
          <button
            id="accept_user"
            name="pending"
            value="0"
            type="submit"
            class="btn btn-success"
            style="width: 48%;"
          >Accept</button>

          <button
            id="reject_user"
            name="pending"
            value="1"            
            type="submit"
            class="btn btn-danger"
            style="width: 48%;"
          >Reject</button>
        </div>
      </div>
    % else:
      <%
        blocked = user['blocked'] if 'blocked' in user else False
      %>
      % if blocked:
        <button
          class="btn btn-primary w-100"
          name="blocked"
          value="0"
          type="submit"
        >Unblock</button>
      % else:
        <button
          class="btn btn-primary w-100"
          name="blocked"
          value="1"
          type="submit"
        >Block</button>
      % endif
    % endif
  </form>
</div>

<script
  src="/js/toggle_password.js?v=${cache_busters['js/toggle_password.js']}"
  integrity="sha384-${cache_busters['js/toggle_password.js']}"
  crossorigin="anonymous"
></script>
