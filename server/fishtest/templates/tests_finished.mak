<%inherit file="base.mak"/>
<%
  title = ""
  if "ltc_only" in request.url:
      title += " LTC"
  if "success_only" in request.url:
      title += " Greens"
  if "yellow_only" in request.url:
      title += " Yellows"
%>

<%!
  title = "Finished Tests | Stockfish Testing"
%>

<%block name="head">
  <meta property="og:title" content="${title}" />
  <meta property="og:description" content="Finished - ${num_finished_runs} tests" />
</%block>

<script>
  document.title =  '${title}';
</script>

% if 'success_only' in request.url and 'yellow_only' in request.url:
  <div class="alert alert-danger">Invalid parameters</div>
% else:
  <h2>Finished Tests -${title}</h2>

  <%include file="run_table.mak" args="runs=finished_runs,
                                       header='Finished',
                                       count=num_finished_runs,
                                       pages=finished_runs_pages,
                                       title=title"
  />
% endif
