<%inherit file="base.mak"/>

<form class="form-horizontal" action="${request.url}" method="POST">
  <legend>Stockfish test run</legend>
  <div class="control-group">
    <label class="control-label">Base branch:</label>
    <div class="controls">
      <input name="base-branch" value="master">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test branch:</label>
    <div class="controls">
      <input name="test-branch">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label"># of games:</label>
    <div class="controls">
      <input name="num-games" value="16000">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">TC:</label>
    <div class="controls">
      <input name="tc" value="15+0.05">
    </div>
  </div>
  <div class="control-group">
    <div class="controls">
      <button type="submit" class="btn btn-primary">Start</button>
    </div>
  </div>
</form>
