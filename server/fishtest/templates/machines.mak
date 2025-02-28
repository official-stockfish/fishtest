<%!
  from fishtest.util import format_time_ago, worker_name

  def clip_long(text, max_length=20):
      if len(text) > max_length:
          return text[:max_length] + "..."
      else:
          return text
%>

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
    % for machine in machines_list:
      <%
        gcc_version = ".".join([str(m) for m in machine['gcc_version']])
        compiler = machine.get('compiler', 'g++')
        python_version = ".".join([str(m) for m in machine['python_version']])
        version = str(machine['version']) + "*" * machine['modified']
        worker_name_ = worker_name(machine, short=True)
        formatted_time_ago = format_time_ago(machine["last_updated"])
        sort_value_time_ago = -machine['last_updated'].timestamp()
        branch = machine['run']['args']['new_tag']
        task_id = str(machine['task_id'])
        run_id = str(machine['run']['_id'])
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
        <td><a href="/workers/${worker_name_}">${machine['unique_key'].split('-')[0]}</a></td>
        <td>${f"{machine['nps'] / 1000000:.2f}"}</td>
        <td>${machine['max_memory']}</td>
        <td>${machine['uname']}</td>
        <td>${compiler} ${gcc_version}</td>
        <td>${python_version}</td>
        <td>${version}</td>
        <td>
          <a href="/tests/view/${run_id + '?show_task=' + task_id}" title="${branch + "/" + task_id}">${clip_long(branch) + "/" + task_id}</a>
        </td>
        <td data-sort-value="${sort_value_time_ago}">${formatted_time_ago}</td>
      </tr>
    % endfor
    % if "version" not in locals():
      <tr id="no-machines">
        <td colspan=20>No machines running</td>
      </tr>
    % endif
  </tbody>
</table>
