<%inherit file="base.mak"/>

<script>
  document.title = "GitHub Rate Limits | Stockfish Testing";
</script>

<h2>GitHub Rate Limits</h2>

<table class="table table-striped table-sm">
  <thead>
    <tr>
      <th>Server</th>
      <th>Client</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>${remaining}</td>
      <td id="client_rate_limit"></td>
    </tr>
  </tbody>
</table>
<p>
  If you are frequently hitting the client rate limit then it is recommended to
  install a
  <a href="https://github.com/settings/personal-access-tokens" target="_blank">
    GitHub personal access token
  </a>
  in your
  <a href="/user"> profile </a>.
</p>
<script>
  (async () => {
    await DOMContentLoaded();
    const elt = document.getElementById("client_rate_limit");
    elt.innerHTML = await rateLimit();
  })();
</script>
