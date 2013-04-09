<%inherit file="base.mak"/>

<h2>Stockfish Testing Queue</h2>

<h3>Pending - ${len(runs['pending'])} tests ${pending_hours} hrs <button id="pending-button" class="btn" data-toggle="collapse" data-target="#pending">Show</button></h3>
<div class="collapse" id="pending">
%if len(runs['pending']) == 0:
  None
%else:
  <%include file="run_table.mak" args="runs=runs['pending'], show_delete=True"/>
%endif
</div>

%if len(runs['failed']) > 0:
<h3>Failed</h3>
<%include file="run_table.mak" args="runs=runs['failed'], show_delete=True"/>
%endif

<h3>Active - ${len(machines)} machines ${cores} cores</h3>
<table class="table table-striped table-condensed" style="width:70%">
 <thead>
  <tr>
   <th>Machine</th>
   <th>Cores</th>
   <th>MNps</th>
   <th>System</th>
   <th>Version</th>
   <th>Running on</th>
   <th>Last updated</th>
  </tr>
 </thead>
 <tbody>
%for machine in machines:
  <tr>
   <td>${machine['username']}</td>
   <td>${machine['concurrency']}</td>
   <td>${'%.2f' % (machine['nps'] / 1000000.0)}</td>
   <td>${machine['uname'][0]} ${machine['uname'][2]}</td>
   <td>${machine['version']}</td>
   <td><a href="/tests/view/${machine['run']['_id']}">${machine['run']['args']['new_tag']}</td>
   <td>${machine['last_updated']}</td>
  </tr>
%endfor
%if len(machines) == 0:
  <td>No machines running</td>
%endif
 </tbody>
</table>
<%include file="run_table.mak" args="runs=runs['active']"/>

<h3>Finished - ${len(runs['finished'])} tests ${games_played} games </h3>
<%include file="run_table.mak" args="runs=runs['finished']"/>

<script type="text/javascript">
if ($.cookie('pending_state') == 'Hide') {
  $('#pending').addClass('in');
  $('#pending-button').text('Hide');
}

$("#pending-button").click(function() {
  var active = $(this).text() == 'Hide';
  $(this).text(active ? 'Show' : 'Hide');
  $.cookie('pending_state', $(this).text());
});
</script>
