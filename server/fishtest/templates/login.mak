<%inherit file="base.mak"/>

## Remove this when base.mak has the viewport meta tag
<%block name="head">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</%block>

<script>
  document.title = 'Login | Stockfish Testing';
</script>

<div id="login">
  <header class="text-md-center py-2">
    <h2>Login</h2>
    <div class="alert alert-info">
      Don't have an account? 
      <strong><a href="/signup" class="alert-link">Sign up</a></strong>
    </div>
  </header>

  <form action="" method="POST">
    <div class="form-floating mb-3">
      <input
        type="text"
        class="form-control mb-3"
        id="username"
        name="username"
        placeholder="Username"
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
      />
      <label for="password" class="d-flex align-items-end">Password</label>
    </div>

    <div class="mb-3 form-check">
      <label for="staylogged">Remember me</label>
      <input
        type="checkbox"
        class="form-check-input"
        id="staylogged"
        name="stay_logged_in"
      />
    </div>

    <button type="submit" class="btn btn-primary w-100">Login</button>
  </form>
</div>
