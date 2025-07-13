<%inherit file="base.mak"/>

<script>
  document.title = "GitHub Rate Limits | Stockfish Testing";
</script>


<div id="rate_limits_div" hidden="true">
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
        <td id="server_rate_limit">-1</td>
        <td id="server_reset">00:00:00</td>
        <td id="client_rate_limit">-1</td>
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
    const errorCSS = "color: red;";
    const refreshTime = 60000; // 1 minute
    let serverRateLimit = { remaining: -1, reset: 0 };
    let lastClientRefreshTime = 0;
    let lastServerRefreshTime = 0;

    await DOMContentLoaded();
    const clientRateLimitDom = document.getElementById("client_rate_limit");
    const clientResetDom = document.getElementById("client_reset");
    const serverRateLimitDom = document.getElementById("server_rate_limit");
    const serverResetDom = document.getElementById("server_reset");
    const rateLimitsDivDom = document.getElementById("rate_limits_div");
    while(true) {
      let now = Date.now();
      try {
        if (now - lastServerRefreshTime > refreshTime) {
          serverRateLimit = await fetchJson("/api/rate_limit", {signal: abortTimeout(3000)});
          serverRateLimitDom.innerHTML = serverRateLimit.remaining;
          serverResetDom.innerHTML = (new Date(1000 * serverRateLimit.reset)).toLocaleTimeString();
          serverRateLimitDom.style.cssText = "";
          serverResetDom.style.cssText = "";
          lastServerRefreshTime = now;
        }
      } catch(e) {
        serverRateLimitDom.style.cssText = errorCSS;
        serverResetDom.style.cssText = errorCSS;
        log(e);
      }
      try {
        if (now - lastClientRefreshTime > refreshTime) {
          clientRateLimit = await rateLimit();
          clientRateLimitDom.innerHTML = clientRateLimit.remaining;
          clientResetDom.innerHTML = (new Date(1000 * clientRateLimit.reset)).toLocaleTimeString();
          clientRateLimitDom.style.cssText = "";
          clientResetDom.style.cssText = "";
          lastClientRefreshTime = now;
        }
      } catch(e) {
        clientRateLimitDom.style.cssText = errorCSS;
        clientResetDom.style.cssText = errorCSS;
        log(e);
      }
      rateLimitsDivDom.hidden = false;
      await asyncSleep(5000); // 5 seconds
    }
  })();
</script>
