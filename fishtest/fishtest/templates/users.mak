<%inherit file="base.mak"/>
<h4> </h4>
<ul class="inline">
<li><dl class="dl-horizontal">
  <dt>Testers</dt>
  <dd>${sum(u['last_updated'] != 'Never' for u in users)}</dd>
  <dt>Developers</dt>
  <dd>${sum(u['tests'] > 0 for u in users)}</dd>
</dl></li>
<li><dl class="dl-horizontal">
  <dt>Active testers</dt>
  <dd>${sum(u['games_per_hour'] > 0 for u in users)}</dd>
  <dt>Tests submitted</dt>
  <dd>${sum(u['tests'] for u in users)}</dd>
</li></dl>
<li><dl class="dl-horizontal">
  <dt>Games played</dt>
  <dd>${sum(u['games'] for u in users)}</dd>
  <dt>CPU time</dt>
  <dd>${'%.2f years' % (sum(u['cpu_hours'] for u in users)/(24*365))}</dd>
</li></dl>
</ul>

<table class="table table-striped table-condensed">
 <thead>
  <tr>
   <th>Username</th>
   <th>Last active</th>
   <th>Games/Hour</th>
   <th>CPU Hours</th>
   <th>Games played</th>
   <th>Tests submitted</th>
   <th>Tests repository</th>
  </tr>
 </thead>
 <tbody>
 %for user in users:
  <tr>
   <td>${user['username']}</td>
   <td>${user['last_updated']}</td>
   <td>${int(user['games_per_hour'])}</td>
   <td>${int(user['cpu_hours'])}</td>
   <td>${int(user['games'])}</td>
   <td><a href="/tests/user/${user['username']}">${user['tests']}</td>
   <td><a href="${user['tests_repo']}" target="_blank">${user['tests_repo']}</a></td>
  </tr>
 %endfor
 </tbody>
</table>
