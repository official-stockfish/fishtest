<%inherit file="base.mak"/>

<form class="form-horizontal" action="${request.url}" method="POST">
  <legend>Create New Test</legend>
  <!--
  <div class="control-group">
    <label class="control-label">Run name:</label>
    <div class="controls">
      <input name="run-name">
    </div>
  </div>
  -->
  <div class="control-group">
    <label class="control-label">Base branch:</label>
    <div class="controls">
      <input name="base-branch" value="master">
    </div>
    <label class="control-label">signature:</label>
    <div class="controls">
      <input name="base-signature">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test branch:</label>
    <div class="controls">
      <input name="test-branch">
    </div>
    <label class="control-label">signature:</label>
    <div class="controls">
      <input name="test-signature">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Number of games:</label>
    <div class="controls">
      <input name="num-games" value="16000">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Time Control:</label>
    <div class="controls">
      <input name="tc" value="15+0.05">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Run info:</label>
    <div class="controls">
      <input name="run-info">
    </div>
  </div>
  <div class="control-group">
    <div class="controls">
      <button type="submit" class="btn btn-primary">Submit</button>
    </div>
  </div>
</form>
