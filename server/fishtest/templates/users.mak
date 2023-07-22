<%inherit file="base.mak"/>

<%!
  import urllib
%>

<script>
  document.title = 'Users${" - Top Month" if "monthly" in request.url else ""} | Stockfish Testing';
</script>

<h2>
  Users
  % if 'monthly' in request.url:
    - Top Month
  % endif
</h2>

<div class="row g-3 mb-3">
  <div class="col-6 col-sm">
    <div class="card card-lg-sm text-center">
      <div class="card-header text-nowrap" title="Testers">Testers</div>
      <div class="card-body">
        <h4 class="card-title mb-0 monospace">
          ${sum(u['str_last_updated'] != 'Never' for u in users)}
        </h4>
      </div>
    </div>
  </div>

  <div class="col-6 col-sm">
    <div class="card card-lg-sm text-center">
      <div class="card-header text-nowrap" title="Developers">Developers</div>
      <div class="card-body">
        <h4 class="card-title mb-0 monospace">
          ${sum(u['tests'] > 0 for u in users)}
        </h4>
      </div>
    </div>
  </div>

  <div class="col-6 col-sm">
    <div class="card card-lg-sm text-center">
      <div class="card-header text-nowrap" title="Active testers">Active testers</div>
      <div class="card-body">
        <h4 class="card-title mb-0 monospace">
          ${sum(u['games_per_hour'] > 0 for u in users)}
        </h4>
      </div>
    </div>
  </div>
  
  <div class="col-6 col-sm">
    <div class="card card-lg-sm text-center">
      <div class="card-header text-nowrap" title="CPU years">CPU years</div>
      <div class="card-body">
        <h4 class="card-title mb-0 monospace">
          ${f"{sum(u['cpu_hours'] for u in users)/(24*365):.2f}"}
        </h4>
      </div>
    </div>
  </div>

  <div class="col-6 col-sm">
    <div class="card card-lg-sm text-center">
      <div class="card-header text-nowrap" title="Games played">Games played</div>
      <div class="card-body">
        <h4 class="card-title mb-0 monospace">
          ${sum(u['games'] for u in users)}
        </h4>
      </div>
    </div>
  </div>

  <div class="col-6 col-sm">
    <div class="card card-lg-sm text-center">
      <div class="card-header text-nowrap" title="Tests submitted">Tests submitted</div>
      <div class="card-body">
        <h4 class="card-title mb-0 monospace">
          ${sum(u['tests'] for u in users)}  
        </h4>
      </div>
    </div>
  </div>
</div>

<div class="table-responsive-lg">
  <table class="table table-striped table-sm">
    <thead class="sticky-top">
      <tr>
        <th>Username</th>
        <th class="text-end">Last active</th>
        <th class="text-end">Games/Hour</th>
        <th class="text-end">CPU Hours</th>
        <th class="text-end">Games played</th>
        <th class="text-end">Tests submitted</th>
        <th>Tests repository</th>
      </tr>
    </thead>
    <tbody>
      % for user in users:
        <tr>
          <td>${user['username']}</td>
          <td data-diff="${user['diff']}" class="text-end">${user['str_last_updated']}</td>
          <td class="text-end">${int(user['games_per_hour'])}</td>
          <td class="text-end">${int(user['cpu_hours'])}</td>
          <td class="text-end">${int(user['games'])}</td>
          <td class="text-end">
            <a href="/tests/user/${urllib.parse.quote(user['username'])}">${user['tests']}
          </a></td>
          <td class="user-repo">
            <a href="${user['tests_repo']}" target="_blank" rel="noopener">${user['tests_repo']}</a>
          </td>
        </tr>
      % endfor
    </tbody>
  </table>
</div>
