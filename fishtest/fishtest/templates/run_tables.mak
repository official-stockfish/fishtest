%if page_idx == 0:
  <% pending_approval_runs = [run for run in runs['pending'] if not run['approved']] %>
  <% paused_runs = [run for run in runs['pending'] if run['approved']] %>

  <h3>
    Pending approval - ${len(pending_approval_runs)} tests
    <button id="pending-button" class="btn">
      ${'Hide' if pending_shown else 'Show'}
    </button>
  </h3>

  <div id="pending"
       style="${'' if pending_shown else 'display: none;'}">
    %if pending_approval_runs:
      <%include file="run_table.mak" args="runs=pending_approval_runs, show_delete=True"/>
    %else:
      No tests pending approval
    %endif
  </div>

  <h3>
    Paused - ${len(paused_runs)} tests
    <button id="paused-button" class="btn">
      ${'Hide' if paused_shown else 'Show'}
    </button>
  </h3>

  <div id="paused"
       style="${'' if paused_shown else 'display: none;'}">
    %if paused_runs:
      <%include file="run_table.mak" args="runs=paused_runs, show_delete=True"/>
    %else:
      No paused tests
    %endif
  </div>

  %if len(failed_runs) > 0:
    <h3>Failed</h3>
    <%include file="run_table.mak" args="runs=failed_runs, show_delete=True"/>
  %endif

  <h3>Active - ${len(runs['active'])} tests</h3>
  <%include file="run_table.mak" args="runs=runs['active']"/>
%endif

<h3>Finished - ${num_finished_runs} tests</h3>
<%include file="run_table.mak" args="runs=finished_runs, pages=finished_runs_pages"/>
