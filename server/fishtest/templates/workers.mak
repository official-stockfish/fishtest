<%inherit file="base.mak"/>

<%!
  import datetime
  from urllib.parse import quote
  from fishtest.util import delta_date, diff_date
%>

<script>
  document.title = "Workers Management | Stockfish Testing";

  async function handleToggleWorkers() {
    await DOMContentLoaded();
    const originalTable = document
      .getElementById("workers-table")
      .cloneNode(true);

    const originalRows = Array.from(originalTable.querySelectorAll("tbody tr"));

    const all = (row, _inputValue) => true;
    const olderThan5Days = (row, _inputValue) => {
      const cells = Array.from(row.querySelectorAll("td"));
      return cells.some((cell) => {
        const cellText = cell.textContent || cell.innerText;
        if (cellText.toLowerCase().includes("days ago")) {
          const daysAgo = parseInt(cellText);
          return daysAgo > 5;
        }
        return false;
      });
    };

    const notOlderThan5Days = (row, _inputValue) => {
      return !olderThan5Days(row, _inputValue);
    };

    filterTable("dummy", "workers-table", originalRows, notOlderThan5Days);
    document
      .getElementById("workers-table").classList.remove("d-none");

    const tableHandlers =
      [...document.getElementById("workers-table-handler").querySelectorAll(".dropdown-item")];
    tableHandlers.forEach((tableHandler) => {
      tableHandler.addEventListener("click", (e) => {
        const selected = e.target.dataset.handleTargetCustom;
        if (selected === "all-workers")
          filterTable("dummy", "workers-table", originalRows, all);
        else if (selected === "gt-5days")
          filterTable("dummy", "workers-table", originalRows, olderThan5Days);
        else if (selected === "le-5days")
          filterTable("dummy", "workers-table", originalRows, notOlderThan5Days);

        document.getElementById("workers-table-toggle").textContent = e.target.textContent;
      })
    })
  }

  handleToggleWorkers();

</script>

<h2>Workers Management</h2>

% if show_admin:
  <h3>${worker_name}</h3>
  <form method="POST">
    <div class="mb-3">Last changed: ${delta_date(diff_date(last_updated)) if last_updated is not None else "Never"}</div>
    <div class="mb-3">
      <label for="messageInput" class="form-label">Issue</label>
      <textarea
        id="messageInput"
        rows="4" class="form-control"
        placeholder="Describe the issue here" name="message"
      >${message}</textarea>
    </div>
    <div class="mb-3 form-check">
      <label class="form-check-label" for="blockWorker">Blocked</label>
      <input
        type="checkbox"
        class="form-check-input"
        id="blockWorker"
        name="blocked" ${"checked" if blocked else ""}
      >
    </div>
    <button
      type="submit"
      name="submit"
      value="Submit"
      class="btn btn-primary"
    >Submit</button>
    <button type="submit" name="sumbit" class="btn btn-secondary">Cancel</button>
  </form>
  <hr>
% endif  ## show_admin

<h3>Blocked workers</h3>

<div id="workers-table-handler" class="dropdown">
  <button
    id="workers-table-toggle"
    class="btn btn-secondary dropdown-toggle"
    type="button"
    data-bs-toggle="dropdown"
    aria-expanded="false"
  >Modified &#8804; 5 days ago</span></button>

  <ul class="dropdown-menu">
    <li><span class="dropdown-item" data-handle-target-custom="all-workers">All</span></li>
    <li><span class="dropdown-item" data-handle-target-custom="le-5days">Modified &#8804; 5 days ago</span></li>
    <li><span class="dropdown-item" data-handle-target-custom="gt-5days">Modified &gt; 5 days ago</span></li>
  </ul>
</div>

<table id="workers-table" class="table table-striped table-sm d-none">
  <thead>
    <tr>
      <th>Worker</th>
      <th>Last changed</th>
      <th>Events</th>
      % if show_email:
        <th>Email</th>
      % endif
    </tr>
  </thead>
  <tbody>
    % if len(blocked_workers) == 0:
      <tr>
        <td colspan="4">No blocked workers</td>
      </tr>
    % else:
      % for w in blocked_workers:
        <tr>
          <td><a href="/workers/${w['worker_name']}">${w["worker_name"]}</td>
          <td>${delta_date(diff_date(w["last_updated"])) if w["last_updated"] is not None else "Never"}</td>
          <td>
            <a
              href="/actions?text=%22${w['worker_name']}%22">/actions?text="${w['worker_name']}"</a
            >
          </td>
          % if show_email:
            <td>
              <a
                href="mailto:${w['owner_email']}?subject=${quote(w['subject'])}&body=${quote(w['body'].replace('\n','\r\n'))}" target="_blank" rel="noopener noreferrer">${w['owner_email']}
              </a>
          % endif
        </tr>
      % endfor
    % endif
  </tbody>
</table>
