<%inherit file="base.mak"/>

<div>
<form class="form-horizontal" action="" method="POST">
  <legend>Create new user</legend>
  <div class="control-group">
    <label class="control-label">Username:</label>
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
    <label class="control-label">E-mail:</label>
    <div class="controls">
      <input name="email" />
    </div>
  </div>
  <div class="control-group">
    <div class="controls">
      <button type="submit" name="form.submitted" class="btn btn-primary">Create User</button>
    </div>
  </div>
</form>
</div>
