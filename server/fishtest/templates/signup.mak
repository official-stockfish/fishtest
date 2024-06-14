<%inherit file="base.mak"/>

<script>
  document.title = "Register | Stockfish Testing";
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

  <form method="POST">
    <input type="hidden" name="csrf_token" value="${request.session.get_csrf_token()}">

    <div class="form-floating mb-3">
      <input
        type="text"
        class="form-control mb-3"
        id="username"
        name="username"
        placeholder="Username"
        pattern="[A-Za-z0-9]{2,}"
        title="Only letters and digits and at least 2 long"
        required
        autofocus
      >
      <label for="username" class="d-flex align-items-end">Username</label>
    </div>

    <div class="input-group mb-3">
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
        >
        <label for="password" class="d-flex align-items-end">Password</label>
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
          required
        >
        <label for="password2" class="d-flex align-items-end">Repeat Password</label>
      </div>
      <span class="input-group-text toggle-password-visibility" role="button">
        <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
      </span>
    </div>

    <div class="form-floating mb-3">
      <input
        type="email"
        class="form-control mb-3"
        id="email"
        name="email"
        placeholder="Email"
        required
      >
      <label for="email" class="d-flex align-items-end">Email</label>
    </div>

    <div class="input-group mb-3">
      <div class="form-floating">
        <input
          class="form-control"
          id="tests_repo"
          name="tests_repo"
          placeholder="GitHub Stockfish fork URL"
        >
        <label for="tests_repo" class="d-flex align-items-end">Tests Repository</label>
      </div>
      <span class="input-group-text" role="button" data-bs-toggle="modal" data-bs-target="#tests_repo_info_modal">
        <i class="fas fa-question-circle fa-lg pe-none" style="width: 30px"></i>
      </span>
    </div>

    <div id="tests_repo_info_modal" class="modal fade" tabindex="-1" aria-labelledby="tests_repo_info_modal_label" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-body">
          This Github fork URL will be the default fork URL for users who want to contribute code when creating runs,
           it is not needed for resources contribution.
          </div>
        </div>
      </div>
    </div>

    <div class="g-recaptcha mb-3"
         data-sitekey="6LcnefYpAAAAAFIklIgGGdKKOWc7Dl9ARq7U71U5"></div>

    <button type="submit" class="btn btn-primary w-100">Register</button>
  </form>
</div>

<script
  src="/js/toggle_password.js?v=${cache_busters['js/toggle_password.js']}"
  integrity="sha384-${cache_busters['js/toggle_password.js']}"
  crossorigin="anonymous"
></script>
