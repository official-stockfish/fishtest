<%inherit file="base.mak"/>

<script>
  document.title = "Neural Network Repository | Stockfish Testing";
</script>

<h2>Neural Network Repository</h2>

<p>
  These networks are freely available for download and sharing under a
  <a href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.<br><br>
  Nets colored <span class="default-net">green</span> in the table have passed fishtest testing
  and achieved the status of <i>default net</i> during the development of Stockfish.<br><br>
  The recommended net for a given Stockfish executable can be found as the default value of the EvalFile UCI option.
</p>

<form class="row mb-3" id="search_nn">
  <div class="col-12 col-md-auto mb-3">
    <label for="network_name" class="form-label">Network</label>
    <input
      id="network_name"
      type="text"
      name="network_name"
      class="form-control"
      placeholder="Network name"
      value="${request.GET.get('network_name', '')}"
    >
  </div>

  <div class="col-12 col-md-auto mb-3">
    <label for="user" class="form-label">Uploaded by</label>
  <input
    id="user"
    type="text"
    name="user"
    class="form-control"
    placeholder="Username"
    value="${request.GET.get('user', '')}"
  >
  </div>

  <div class="col-12 mb-3 d-flex align-items-end">
    <div class="form-check form-check-inline">
      <label class="form-check-label" for="master_only">Only master</label>
      <input
        type="checkbox"
        class="form-check-input"
        id="master_only"
        name="master_only" ${'checked' if master_only else ''}
      >
    </div>
  </div>

  <div class="col-12 col-md-auto mb-3 d-flex align-items-end">
    <button type="submit" class="btn btn-success w-100">Search</button>
  </div>
</form>

<%include file="pagination.mak" args="pages=pages"/>

<div class="table-responsive-lg">
  <table class="table table-striped table-sm">
    <thead class="sticky-top">
      <tr>
        <th>Time</th>
        <th>Network</th>
        <th>Username</th>
        <th>First test</th>
        <th>Last test</th>
        <th style="text-align:right">Downloads</th>
      </tr>
    </thead>
    <tbody>
      % for idx, nn in enumerate(nns):
        % if not master_only or 'is_master' in nn:
          <tr>
            <td>${nn['time'].strftime("%y-%m-%d %H:%M:%S")}</td>
            % if 'is_master' in nn:
              <td class="default-net">
            % else:
              <td>
            % endif
            <a href="api/nn/${nn['name']}" style="font-family:monospace">${nn['name']}</a></td>
            <td>${nn['user']}</td>
            <td>
              % if 'first_test' in nn:
                <a href="tests/view/${nn['first_test']['id']}">${str(nn['first_test']['date']).split('.')[0]}</a>
              % endif
            </td>
            <td>
              % if 'last_test' in nn:
                <a href="tests/view/${nn['last_test']['id']}">${str(nn['last_test']['date']).split('.')[0]}</a>
              % endif
            </td>
            <td style="text-align:right">${nn.get('downloads', 0)}</td>
          </tr>
        % endif
      % endfor
      % if "idx" not in locals():
        <tr>
          <td colspan=20>No nets available</td>
        </tr>
      % endif
    </tbody>
  </table>
</div>

<%include file="pagination.mak" args="pages=pages"/>

<script>
  document
    .getElementById("search_nn")
    .addEventListener("submit", () => {
      const masterOnly = document.getElementById("master_only");
      document.cookie =
        "master_only" + "=" + masterOnly.checked + "; max-age=${60 * 60 * 24 * 365 * 10}; SameSite=Lax";
    });
</script>
