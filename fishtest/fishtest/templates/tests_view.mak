<%inherit file="base.mak"/>

<h2>Run ${run['_id']}</h2>

<%include file="elo_results.mak" args="run=run" />

%for arg, v in sorted(run['args'].iteritems()):
  <div>
    <b>${arg}</b>: ${v}
  </div>
%endfor

<form class="form-horizontal" action="/tests/run_more" method="POST">
  <legend>Adjust number of games</legend>
  <div class="control-group">
    <label class="control-label">Number of games:</label>
    <div class="controls">
      <input name="num-games" value="${run['args']['num_games']}">
    </div>
  </div>
  <input type="hidden" name="run" value="${run['_id']}" />
  <div class="control-group">
    <div class="controls">
      <button type="submit" class="btn btn-primary">Submit</button>
    </div>
  </div>
</form>
