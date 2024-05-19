<%inherit file="base.mak"/>

<script>
  document.title = "User Management | Stockfish Testing";
</script>

<script>
  async function handleGitHubToken() {
    await DOMContentLoaded();
    document.getElementById("github_token").value = localStorage.getItem("github_token") || "";
    document.getElementById("profile_form").addEventListener("submit", (e) => {
        e.preventDefault();
        const githubToken = document.getElementById("github_token").value;
        localStorage.setItem("github_token", githubToken);
        e.target.submit();
    });
  }
  handleGitHubToken();
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>User Management</h2>
    <div class="alert alert-info">
      <h4 class="alert-heading">
        <a href="/tests/user/${user['username']}" class="alert-link col-6 text-break">${user['username']}</a>
      </h4>
      <ul class="list-group list-group-flush">
        % if not profile:
          <li class="list-group-item bg-transparent text-break">Email: 
            <a href="mailto:${user['email']}?Subject=Fishtest%20Account" class="alert-link">
              ${user['email']}
            </a>
          </li>
        % endif
        <li class="list-group-item bg-transparent text-break">Registered: ${format_date(user['registration_time'] if 'registration_time' in user else 'Unknown')}</li>
        <li class="list-group-item bg-transparent text-break">Machine Limit: ${limit}</li>
        <li class="list-group-item bg-transparent text-break">CPU-Hours: ${hours}</li>
      </ul>
    </div>
  </header>

  <form id="profile_form" action="${request.url}" method="POST">
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
            name="old_password"
            placeholder="Password"
            required
          />
          <label for="password" class="d-flex align-items-end">Password</label>
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
            id="password"
            name="password"
            placeholder="New Password"
            pattern=".{8,}"
            title="Eight or more characters: a password too simple or trivial to guess will be rejected"
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
          />
          <label for="password2" class="d-flex align-items-end">Repeat Password</label>
        </div>
        <span class="input-group-text toggle-password-visibility" role="button">
          <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
        </span>
      </div>

      <div class="input-group mb-3">
        <div class="form-floating">
          <input
            class="form-control"
            id="github_token"
            name="github_token"
            autocomplete="off"
           placeholder="GitHub's fine-grained personal access token"
          />
        <label for="github_token" class="d-flex align-items-end">GitHub's fine-grained personal access token</label>
        </div>
        <span class="input-group-text" role="button" data-bs-toggle="modal" data-bs-target="#infoModal">
          <i class="fas fa-question-circle fa-lg pe-none" style="width: 30px"></i>
        </span>
      </div>

      <div class="modal fade" id="infoModal" tabindex="-1" aria-labelledby="infoModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-body">
              <!-- Explanation about token purpose -->
              <p>The purpose of this token is to authenticate your requests to GitHub's API, 
              which has a rate limit of 60 requests per hour for unauthenticated users. By using this token, 
              you can increase this limit to 5000 requests per hour. More information about GitHub's rate limits can be found 
              <a href="https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting" target="_blank">here</a>.
              </p>
              
              <!-- Information about storage -->
              <p>This token will be stored in your local storage, not in the server database.
              This ensures that the token is only accessible to you, reducing the risk of unauthorized access.
              </p>
              
              <!-- Permissions and access information -->
              <p>The token should be granted the minimum permissions necessary for your use case. 
              This reduces the potential impact if the token is accidentally exposed or misused.
              </p>
              
              <!-- Instructions on how to obtain the token -->
              <h4>Instructions:</h4>
              <ol>
                <li>Access the Github's link <a href="https://github.com/settings/tokens?type=beta" target="_blank">here</a>, login if required.</li>
                <li>Press "Generate a new token".</li>
                <li>Set a "Token name".</li>
                <li>Set your preferred "Expiration" time.</li>
                <li>Set "Repository access" to "Public Repositories (read-only)".</li>
                <li>Press "Generate token" at the bottom of the page.</li>
                <li>Copy the token and paste it into this input field. Remember, GitHub will not show the token again for security reasons, so make sure to save it somewhere safe.</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
      <button type="submit" class="btn btn-primary w-100">Save</button>
    % elif 'pending' in user and user['pending']:
      <div class="alert alert-dark mb-3">
        <label class="mb-2 h5">User Approval:</label>
        <div class="w-100 d-flex justify-content-between">
          <button
            id="reject_user"
            name="pending"
            value="1"
            type="submit"
            class="btn btn-danger"
            style="width: 48%;"
          >Reject</button>

          <button
            id="accept_user"
            name="pending"
            value="0"
            type="submit"
            class="btn btn-success"
            style="width: 48%;"
          >Accept</button>
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
