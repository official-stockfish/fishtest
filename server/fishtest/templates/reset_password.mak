<%inherit file="base.mak"/>

<script>
  document.title = "Reset Password | Stockfish Testing";
</script>


<%block name="head">
  <script src='https://www.google.com/recaptcha/api.js'></script>
</%block>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>Choose a new password</h2>
  </header>

  <form method="POST">
    <div class="input-group mb-3">
      <div class="form-floating">
        <input
          type="password"
          class="form-control"
          id="password"
          name="password"
          placeholder="New Password"
          pattern=".{8,}"
          title="Eight or more characters: a password too simple or trivial to guess will be rejected"
          autocomplete="new-password"
          required
          autofocus
        >
        <label for="password" class="d-flex align-items-end">New Password</label>
      </div>
      <span class="input-group-text toggle-password-visibility" role="button">
        <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
      </span>
    </div>

    <div class="input-group mb-3">
      <div class="form-floating">
        <input
          type="password"
          class="form-control"
          id="password2"
          name="password2"
          placeholder="Repeat Password"
          autocomplete="new-password"
          required
        >
        <label for="password2" class="d-flex align-items-end">Repeat Password</label>
      </div>
      <span class="input-group-text toggle-password-visibility" role="button">
        <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
      </span>
    </div>

    <div class="g-recaptcha mb-3"
         data-sitekey="6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"></div>

    <button type="submit" class="btn btn-primary w-100">Reset password</button>
  </form>
</div>

<script src="${request.static_url('fishtest:static/js/toggle_password.js')}"></script>
