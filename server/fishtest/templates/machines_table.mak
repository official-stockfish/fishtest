<table class="table table-striped table-sm">
  <thead class="sticky-top">
    <tr>
      <th>Machine</th>
      <th>Cores</th>
      <th>UUID</th>
      <th>MNps</th>
      <th>RAM</th>
      <th>System</th>
      <th>Compiler</th>
      <th>Python</th>
      <th>Worker</th>
      <th>Running on</th>
      <th>Last updated</th>
    </tr>
  </thead>
  <tbody>
    % for machine in machines:
        <%
          gcc_version = ".".join([str(m) for m in machine['gcc_version']])
          compiler = machine.get('compiler', 'g++')
          python_version = ".".join([str(m) for m in machine['python_version']])
          version = str(machine['version']) + "*" * machine['modified']
        %>
        <tr>
          <td>${machine['username']}</td>
          <td>
            % if 'country_code' in machine:
                <div class="flag flag-${machine['country_code'].lower()}"
                     style="display: inline-block"></div>
            % endif
            ${machine['concurrency']}
          </td>
          <td>${machine['unique_key'].split('-')[0]}</td>
          <td>${f"{machine['nps'] / 1000000:.2f}"}</td>
          <td>${machine['max_memory']}</td>
          <td>${machine['uname']}</td>
          <td>${compiler} ${gcc_version}</td>
          <td>${python_version}</td>
          <td>${version}</td>
          <td>
            <a href="/tests/view/${machine['run']['_id']}">${machine['run']['args']['new_tag']}</a>
          </td>
          <td>${machine['last_updated']}</td>
        </tr>
    % endfor
    % if len(machines) == 0:
        <td colspan=20>No machines running</td>
    % endif
  </tbody>
</table>
