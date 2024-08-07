<%inherit file="base.mak"/>

<script>
  document.title = "Register | Stockfish Testing";
</script>

<%block name="head">
  <script src='https://www.google.com/recaptcha/api.js'></script>
</%block>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2 id="register-heading">Register</h2>
    <div class="alert alert-info" role="alert">
      <h4 class="alert-heading">Manual Approvals</h4>
      <p class="mb-0">To avoid spam, a person will manually approve your account.</p>
      <p class="mb-0">This is usually quick but <strong>sometimes takes a few hours</strong>.</p>
      <hr />
      <p class="mb-0">Already have an account? <strong><a href="/login" class="alert-link">Log in</a></strong></p>
    </div>
  </header>

  <form method="POST" aria-labelledby="register-heading">
    <input type="hidden" name="csrf_token" value="${request.session.get_csrf_token()}">

    <div class="form-floating mb-3">
      <input
        type="text"
        class="form-control"
        id="username"
        name="username"
        placeholder="Username"
        pattern="[A-Za-z0-9]{2,}"
        title="Only letters and digits and at least 2 characters long"
        required
        aria-describedby="username-help"
        autofocus
      >
      <label for="username">Username</label>
      <div id="username-help" class="form-text">Only letters and digits and at least 2 characters long.</div>
    </div>

    <div class="input-group mb-3 has-validation">
      <div class="form-floating">
        <input
          type="password"
          class="form-control"
          id="password"
          name="password"
          placeholder="Password"
          pattern=".{8,}"
          title="Eight or more characters: a password too simple or trivial to guess will be rejected"
          required
          aria-describedby="password-help"
        >
        <label for="password">Password</label>
      </div>
      <span class="input-group-text toggle-password-visibility" role="button" aria-label="Toggle password visibility">
        <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
      </span>
      <div id="password-help" class="form-text">Eight or more characters: a password too simple or trivial to guess will be rejected.</div>
    </div>

    <div class="input-group mb-3 has-validation">
      <div class="form-floating">
        <input
          type="password"
          class="form-control"
          id="password2"
          name="password2"
          placeholder="Repeat Password"
          pattern=".{8,}"
          required
          aria-describedby="password2-help"
        >
        <label for="password2">Repeat Password</label>
      </div>
      <span class="input-group-text toggle-password-visibility" role="button" aria-label="Toggle password visibility">
        <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
      </span>
      <div id="password2-help" class="form-text">Please repeat your password.</div>
    </div>

    <div class="form-floating mb-3">
      <input
        type="email"
        class="form-control"
        id="email"
        name="email"
        placeholder="Email"
        required
        aria-describedby="email-help"
      >
      <label for="email">Email</label>
      <div id="email-help" class="form-text">Enter a valid email address.</div>
    </div>

    <div class="input-group mb-3">
      <div class="form-floating">
        <input
          class="form-control"
          id="tests_repo"
          name="tests_repo"
          placeholder="GitHub Stockfish fork URL"
          aria-describedby="tests_repo_help"
        >
        <label for="tests_repo">Tests Repository</label>
      </div>
      <span
        class="input-group-text"
        role="button"
        data-bs-toggle="modal"
        data-bs-target="#tests_repo_info_modal"
        aria-label="More information about Tests Repository"
        aria-haspopup="dialog"
      >
        <i class="fas fa-question-circle fa-lg pe-none" style="width: 30px"></i>
      </span>
    </div>

    <div id="tests_repo_info_modal" class="modal fade" tabindex="-1" aria-labelledby="tests_repo_info_modal_label" role="dialog">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-body">
          This Github fork URL will be the default fork URL for users who want to contribute code when creating runs,
           it is not needed for resources contribution.
          </div>
        </div>
      </div>
    </div>

    <div class="g-recaptcha mb-3" data-sitekey="6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"></div>

    <button type="submit" class="btn btn-primary w-100">Register</button>
  </form>
</div>

<script
  src="/js/toggle_password.js?v=${cache_busters['js/toggle_password.js']}"
  integrity="sha384-${cache_busters['js/toggle_password.js']}"
  crossorigin="anonymous"
></script>
