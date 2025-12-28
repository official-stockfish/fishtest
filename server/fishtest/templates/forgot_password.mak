<%inherit file="base.mak"/>

<script>
  document.title = "Forgot Password | Stockfish Testing";
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>Reset your password</h2>
    <div class="alert alert-info">
      Enter the email linked to your account and we'll send a reset link.
    </div>
  </header>

  <form method="POST">
    <div class="form-floating mb-3">
      <input
        type="email"
        class="form-control mb-3"
        id="email"
        name="email"
        placeholder="Email"
        autocomplete="email"
        required
        autofocus
      >
      <label for="email" class="d-flex align-items-end">Email</label>
    </div>

    <button type="submit" class="btn btn-primary w-100">Send reset link</button>
  </form>

  <div class="text-center mt-3">
    <a href="${request.route_url('login')}" class="alert-link">Back to login</a>
  </div>
</div>
