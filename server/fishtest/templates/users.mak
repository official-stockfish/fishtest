<%inherit file="base.mak"/>

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
      <div class="col text-end"><b>Testers</b></div>
      <div class="col text-start">
        ${sum(u['last_updated'] != 'Never' for u in users)}
      </div>
    </div>
    <div class="row">
      <div class="col text-end"><b>Developers</b></div>
      <div class="col text-start">
        ${sum(u['tests'] > 0 for u in users)}
      </div>
    </div>
  </div>

  <div class="col-sm">
    <div class="row">
      <div class="col text-end"><b>Active testers</b></div>
      <div class="col text-start">
        ${sum(u['games_per_hour'] > 0 for u in users)}
      </div>
    </div>
    <div class="row">
      <div class="col text-end"><b>Tests submitted</b></div>
      <div class="col text-start">
        ${sum(u['tests'] for u in users)}
      </div>
    </div>
  </div>

  <div class="col-sm">
    <div class="row">
      <div class="col text-end"><b>Games played</b></div>
      <div class="col text-start">
        ${sum(u['games'] for u in users)}
      </div>
    </div>
    <div class="row">
      <div class="col text-end"><b>CPU time</b></div>
      <div class="col text-start">
        ${f"{sum(u['cpu_hours'] for u in users)/(24*365):.2f} years"}
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
            <td data-diff="${user['diff']}" class="text-end">${user['last_updated']}</td>
            <td class="text-end">${int(user['games_per_hour'])}</td>
            <td class="text-end">${int(user['cpu_hours'])}</td>
            <td class="text-end">${int(user['games'])}</td>
            <td class="text-end"><a href="/tests/user/${user['username']}">${user['tests']}</td>
            <td class="user-repo"><a href="${user['tests_repo']}" target="_blank" rel="noopener">${user['tests_repo']}</a></td>
          </tr>
      % endfor
    </tbody>
  </table>
</div>
