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

<div class="row" style="padding: 1em 0">
  <div class="col-sm">
    <div class="row">
      <div class="col text-center"><b>Testers</b></div>
      <div class="col text-start">
        ${sum(u['str_last_updated'] != 'Never' for u in users)}
      </div>
    </div>
    <div class="row">
      <div class="col text-center"><b>Developers</b></div>
      <div class="col text-start">
        ${sum(u['tests'] > 0 for u in users)}
      </div>
    </div>
  </div>

  <div class="col-sm">
    <div class="row">
      <div class="col text-center"><b>Active testers</b></div>
      <div class="col text-start">
        ${sum(u['games_per_hour'] > 0 for u in users)}
      </div>
    </div>
    <div class="row">
      <div class="col text-center"><b>Tests submitted</b></div>
      <div class="col text-start">
        ${sum(u['tests'] for u in users)}
      </div>
    </div>
  </div>

  <div class="col-sm">
    <div class="row">
      <div class="col text-center"><b>Games played</b></div>
      <div class="col text-start">
        ${sum(u['games'] for u in users)}
      </div>
    </div>
    <div class="row">
      <div class="col text-center"><b>CPU time</b></div>
      <div class="col text-start">
        ${f"{sum(u['cpu_hours'] for u in users)/(24*365):.2f} years"}
      </div>
    </div>
  </div>
</div>

<div class="table-responsive-lg">
  <table class="table table-striped table-sm">
    <thead class="sticky-top users-head">
      <tr>
        <th>Username</th>
        <th>Last active</th>
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
          <td data-diff="${user['diff']}">${user['str_last_updated']}</td>
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
