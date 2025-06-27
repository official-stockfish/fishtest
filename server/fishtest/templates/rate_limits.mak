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
    <td>
      ${remaining}
    </td>
    <td id="client_rate_limit"></td>
    </tr>
  </tbody>
</table>

<script>
  async function showRateLimit(elt) {
    await DOMContentLoaded();
    elt.innerHTML = await rateLimit();
  }
  const elt = document.getElementById("client_rate_limit");
  showRateLimit(elt);
</script>
