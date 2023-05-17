<%!
  import binascii
%>
<%
  # to differentiate toggle states on different pages
  prefix = 'user'+binascii.hexlify(username.encode()).decode()+"_" if username is not Undefined else ""
%>

% if page_idx == 0:
  <%
    pending_approval_runs = [run for run in runs['pending'] if not run['approved']]
    paused_runs = [run for run in runs['pending'] if run['approved']]
  %>

  <%include file="run_table.mak" args="runs=pending_approval_runs,
                                       show_delete=True,
                                       header='Pending approval',
                                       count=len(pending_approval_runs),
                                       toggle=prefix+'pending',
                                       alt='No tests pending approval'"
  />

  <%include file="run_table.mak" args="runs=paused_runs,
                                       show_delete=True,
                                       header='Paused',
                                       count=len(paused_runs),
                                       toggle=prefix+'paused',
                                       alt='No paused tests'"
   />

  <%include file="run_table.mak" args="runs=failed_runs,
                                       show_delete=True,
                                       toggle=prefix+'failed',
                                       count=len(failed_runs),
                                       header='Failed',
                                       alt='No failed tests on this page'"
  />

  <%include file="run_table.mak" args="runs=runs['active'],
                                       header='Active',
                                       toggle=prefix+'active',
                                       count=len(runs['active']),
                                       alt='No active tests'"
  />
% endif

<%include file="run_table.mak" args="runs=finished_runs,
                                     header='Finished',
                                     count=num_finished_runs,
                                     toggle=prefix+'finished' if page_idx==0 else None,
                                     pages=finished_runs_pages"
/>
