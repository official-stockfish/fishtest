<%inherit file="base.mak"/>

<script>
  document.title = "Login | Stockfish Testing";
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>Login</h2>
    <div class="alert alert-info">
      Don't have an account?
      <strong><a href="/signup" class="alert-link">Sign up</a></strong>
    </div>
  </header>

  <form method="POST">
    <div class="form-floating mb-3">
      <input
        type="text"
        class="form-control mb-3"
        id="username"
        name="username"
        placeholder="Username"
        autocomplete="username"
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
          autocomplete="current-password"
          required
        >
        <label for="password" class="d-flex align-items-end">Password</label>
      </div>
      <span class="input-group-text toggle-password-visibility" role="button">
        <i class="fa-solid fa-lg fa-eye pe-none" style="width: 30px"></i>
      </span>
    </div>

    <div class="mb-3 form-check">
      <label class="form-check-label" for="staylogged">Remember me</label>
      <input
        type="checkbox"
        class="form-check-input"
        id="staylogged"
        name="stay_logged_in"
      >
    </div>

    <button type="submit" class="btn btn-primary w-100">Login</button>
  </form>
</div>

<script
  src="/js/toggle_password.js?v=${cache_busters['js/toggle_password.js']}"
  integrity="sha384-${cache_busters['js/toggle_password.js']}"
  crossorigin="anonymous"
></script>
