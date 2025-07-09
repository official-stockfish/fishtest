<%inherit file="base.mak"/>

<script>
  document.title = "GitHub Rate Limits | Stockfish Testing";
</script>


<div id="rate_limits" hidden="true">
  <h2>GitHub Rate Limits</h2>
  <table class="table table-striped table-sm">
    <thead>
      <tr>
        <th>Server</th>
        <th>Reset</th>
        <th>Client</th>
        <th>Reset</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td id="server_rate_limit">0</td>
        <td id="server_reset">00:00:00</td>
        <td id="client_rate_limit">0</td>
        <td id="client_reset">00:00:00</td>
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
</div>
<script>
  (async () => {
    await DOMContentLoaded();
    const clientRateLimitDom = document.getElementById("client_rate_limit");
    const clientResetDom = document.getElementById("client_reset");
    const serverRateLimitDom = document.getElementById("server_rate_limit");
    const serverResetDom = document.getElementById("server_reset");
    const rateLimitsDom = document.getElementById("rate_limits");
    let serverRateLimit = { remaining: -1, reset: 0 };
    while(true) {
      try {
        serverRateLimit = await fetchJson("/api/rate_limit");
      } catch(e) {
        log(e);
      }
      clientRateLimit = await rateLimit();
      clientRateLimitDom.innerHTML = clientRateLimit.remaining;
      serverRateLimitDom.innerHTML = serverRateLimit.remaining;
      clientResetDom.innerHTML = (new Date(1000 * clientRateLimit.reset)).toLocaleTimeString();
      serverResetDom.innerHTML = (new Date(1000 * serverRateLimit.reset)).toLocaleTimeString();
      rateLimitsDom.hidden = false;
      await asyncSleep(60000); // 1 minute
    }
  })();
</script>
