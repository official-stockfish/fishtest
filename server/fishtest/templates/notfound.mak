<%inherit file="base.mak"/>

<script>
  document.title = "Page not found";
</script>

<style>
  .error-container {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 82vh;
  }
  .error-content {
    text-align: center;
  }
  .error-heading {
    font-size: 6rem;
    color: #343a40;
    margin-bottom: 1rem;
  }
  .error-message {
    font-size: 1.5rem;
    color: #6c757d;
    margin-bottom: 2rem;
  }
  .error-button {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    background-color: #77828f;
    color: #fff;
    text-decoration: none;
    border-radius: 5px;
    transition: background-color 0.3s;
    border: none;
    cursor: pointer;
    outline: none;
  }
  .error-button:hover {
    background-color: #0056b3;
  }
</style>

<div class="error-container">
  <div class="error-content">
    <h1 class="error-heading">404</h1>
    <h2 class="error-message">Oops! Page not found.</h2>
    <p class="lead">The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.</p>
    <a href="/" class="error-button">Go to Home</a>
  </div>
</div>
