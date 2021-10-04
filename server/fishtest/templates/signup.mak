<%inherit file="base.mak"/>

<%block name="head">
  <script src='https://www.google.com/recaptcha/api.js'></script>
</%block>

<div>
  <p></p>
  <p>Signing up to fishtest allows you to contribute with CPU time or with patches to test.</p>
  <p>Your contribution is much appreciated.</p>
  <p>Once a new user account is created, a human needs to manually activate it. This is usually quick, but sometimes takes a few hours.</p>

  <form class="form-horizontal" action="" method="POST">
    <input type="hidden" name="csrf_token"
           value="${request.session.get_csrf_token()}" />
    <legend>Create new user</legend>

    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 text-end">Username</label>
      <div class="col-sm-3">
        <input name="username" pattern="[A-Za-z0-9]{2,}" type="text"
               title="Only letters and digits and at least 2 long" required="required"
               class="form-control" />
      </div>
    </div>

    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 text-end">Password</label>
      <div class="col-sm-3">
        <input name="password" type="password" pattern=".{8,}"
               title="Eight or more characters: a password too simple or trivial to guess will be rejected"
               required="required"
               class="form-control" />
      </div>
    </div>

    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 text-end">Verify password</label>
      <div class="col-sm-3">
        <input name="password2" type="password" required="required" class="form-control" />
      </div>
    </div>

    <div class="form-group row mb-3">
      <label class="col-form-label col-sm-2 text-end">E-mail</label>
      <div class="col-sm-3">
        <input name="email" type="email" required="required" class="form-control" />
      </div>
    </div>

    <div class="form-group mb-3">
      <div class="col-sm-4 offset-sm-2">
        <div class="g-recaptcha"
             data-sitekey="6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"></div>
      </div>
    </div>

    <div class="form-group row">
      <div class="col-sm-2"></div>
      <div class="col-sm-4">
        <button type="submit" class="btn btn-primary">Create User</button>
      </div>
    </div>

  </form>
</div>
