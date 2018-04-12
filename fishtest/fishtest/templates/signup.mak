<%inherit file="base.mak"/>

<div>
<p>
Note that many modern browsers can generate/remember a strong password for you.
</p>
<p>
If it is not suggested by default you can try right-clicking on the password entry field.
</p>
<form class="form-horizontal" action="" method="POST">
  <legend>Create new user</legend>
  <div class="control-group">
    <label class="control-label">Username:</label>
    <div class="controls">
      <input name="username" required="required"/>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Password:</label>
    <div class="controls">
      <input name="password" type="password" required="required"/>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Repeat password:</label>
    <div class="controls">
      <input name="password2" type="password" required="required"/>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">E-mail:</label>
    <div class="controls">
      <input name="email" type="email" required="required"/>
    </div>
  </div>
  <div class="control-group">
    <div class="controls">
      <button type="submit" name="form.submitted" class="btn btn-primary">Create User</button>
    </div>
  </div>
</form>
</div>
