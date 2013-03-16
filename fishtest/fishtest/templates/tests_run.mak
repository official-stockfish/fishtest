<%inherit file="base.mak"/>

<form class="form-horizontal" action="${request.url}" method="POST">
  <legend>Create New Test</legend>
  <div class="control-group">
    <label class="control-label">Test branch:</label>
    <div class="controls">
      <input name="test-branch">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test signature:</label>
    <div class="controls">
      <input name="test-signature">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Base branch:</label>
    <div class="controls">
      <input name="base-branch" value="master"/>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Base signature:</label>
    <div class="controls">
      <input name="base-signature"/>
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
    <label class="control-label">Threads:</label>
    <div class="controls">
      <input name="threads" value="1">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Book:</label>
    <div class="controls">
      <input name="book" value="varied.bin">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Book Depth:</label>
    <div class="controls">
      <input name="book-depth" value="10">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Notes:</label>
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
