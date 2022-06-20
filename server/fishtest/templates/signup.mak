<%inherit file="base.mak"/>

<script>
  document.title = 'Register | Stockfish Testing';
</script>

<%block name="head">
  <script src='https://www.google.com/recaptcha/api.js'></script>
</%block>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>Register</h2>
    <div class="alert alert-info">
      <h4 class="alert-heading">Manual Approvals</h4>
      <p class="mb-0">To avoid spam, a person will manually approve your account.</p>
      <p class="mb-0">This is usually quick but <strong>sometimes takes a few hours</strong>.</p>
      <hr />
      <p class="mb-0">Already have an account? <strong><a href="/login" class="alert-link">Log in</a></strong></p>
    </div>
  </header>

  <form action="" method="POST">
    <input type="hidden" name="csrf_token"
           value="${request.session.get_csrf_token()}" />

    <div class="form-floating mb-3">
      <input
        type="text"
        class="form-control mb-3"
        id="username"
        name="username"
        placeholder="Username"
        pattern="[A-Za-z0-9]{2,}"
        title="Only letters and digits and at least 2 long"
        required="required"
      />
      <label for="username" class="d-flex align-items-end">Username</label>
    </div>

    <div class="form-floating mb-3">
      <input
        type="password"
        class="form-control mb-3"
        id="password"
        name="password"
        placeholder="Password"
        pattern=".{8,}"
        title="Eight or more characters: a password too simple or trivial to guess will be rejected"
        required="required"
      />
      <label for="password" class="d-flex align-items-end">Password</label>
    </div>

    <div class="form-floating mb-3">
      <input
        type="password"
        class="form-control mb-3"
        id="password2"
        name="password2"
        placeholder="Repeat Password"
        required="required"
      />
      <label for="password2" class="d-flex align-items-end">Repeat Password</label>
    </div>

    <div class="form-floating mb-3">
      <input
        type="email"
        class="form-control mb-3"
        id="email"
        name="email"
        placeholder="Email"
        required="required"
      />
      <label for="email" class="d-flex align-items-end">Email</label>
    </div>

    <div class="g-recaptcha mb-3"
         data-sitekey="6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"></div>

    <button type="submit" class="btn btn-primary w-100">Register</button>
  </form>
</div>
