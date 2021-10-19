<%inherit file="base.mak"/>
<h2>Login</h2>

<div class="alert alert-info alert-block">
  <h4>Permission Required</h4>
  Creating or modifying tests requires you to be logged in.
  If you don't have an account, please
  <a href="/signup">Register</a>.
</div>

<div>
  <form class="form-horizontal" action="" method="POST">
    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 text-end">Username</label>
      <div class="col-sm-3">
        <input name="username" type="text" class="form-control" />
      </div>
    </div>

    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 text-end">Password</label>
      <div class="col-sm-3">
        <input name="password" type="password" class="form-control" />
      </div>
    </div>

    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 form-check-label text-end">Stay logged in</label>
      <div class="col-sm-3">
        <input name="stay_logged_in" type="checkbox" class="form-check-input" />
      </div>
    </div>

    <div class="form-group row">
      <div class="col-sm-2"></div>
      <div class="col-sm-4">
        <button type="submit" class="btn btn-primary">Login</button>
      </div>
    </div>
  </form>
</div>
