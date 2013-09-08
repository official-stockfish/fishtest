<%inherit file="base.mak"/>

<h3>Stockfish testing</h3>
<div class="alert alert-info alert-block">
<h4>Permission Required</h4>
Creating or modifying tests requires special permission.  Please email me at gmail, address: glinscott for access.
</div>

<div>
<form class="form-horizontal" action="" method="POST">
  <legend>Login</legend>
  <div class="control-group">
    <label class="control-label">Login:</label>
    <div class="controls">
      <input name="username"/>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Password:</label>
    <div class="controls">
      <input name="password" type="password" />
    </div>
  </div>
  <div class="control-group">
    <div class="controls">
      <button type="submit" name="form.submitted" class="btn btn-primary">Login</button>
    </div>
  </div>
</form>
</div>
