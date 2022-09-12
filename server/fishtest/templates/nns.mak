<%inherit file="base.mak"/>

<script>
  document.title = 'Neural Network Repository | Stockfish Testing';
</script>

<h2>Neural Network Repository</h2>

<p>
These networks are freely available for download and sharing under a
<a href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.<br><br>
Nets colored <span class="default-net">green</span> in the table have passed fishtest testing
and achieved the status of <i>default net</i> during the development of Stockfish.<br><br>
The recommended net for a given Stockfish executable can be found as the default value of the EvalFile UCI option.
</p>

<script>
  function toggle_nns() {
    const button = document.querySelector("#non_default-button");
    const active = button.innerText.trim().substring(0, 4) === "Hide";
    button.innerText = active ? "Show non default nets" : "Hide non default nets";
    document.cookie =
      "non_default_state=" + (active ? "Hide" : "Show") + ";max-age=315360000;SameSite=Lax;";
    window.location.reload();
  }
</script>
    
<button id="non_default-button" class="btn btn-sm btn-light border" onclick = "toggle_nns()">
  ${'Hide non default nets' if non_default_shown else 'Show non default nets'}
</button>

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
      % for nn in nns:
          % if request.authenticated_userid or 'first_test' in nn:
              % if non_default_shown or 'is_master' in nn:
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
          % endif
      % endfor
    </tbody>
  </table>
</div>
<p>
% if prev_page:
    <a href="nns?page=${prev_page}">&laquo; Newer nets</a>
% endif
% if prev_page and next_page:
    <span>-</span>
% endif
% if next_page:
    <a href="nns?page=${next_page}">Older nets &raquo;</a>
% endif
</p>
