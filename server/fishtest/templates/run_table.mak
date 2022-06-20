<%page args="runs, pages=None, show_delete=False, header=None, count=None, toggle=None, alt=None, title=''"/>

<%namespace name="base" file="base.mak"/>

% if toggle is None:
    <script>
      document.title = '${username + " - " if username else ""}Finished Tests${title} - page ${page_idx+1} | Stockfish Testing';
    </script>
% endif

<%def name="pagination()">
  % if pages and len(pages) > 3:
      <nav>
        <ul class="pagination pagination-sm">
        % for page in pages:
            <li class="${page['state']}">
              % if page['state'] not in ['disabled', 'active']:
                  <a class="page-link" href="${page['url']}">${page['idx']}</a>
              % else:
                  <a class="page-link">${page['idx']}</a>
              % endif
            </li>
        % endfor
        </ul>
      </nav>
  % endif
</%def>

<%
  from fishtest.util import get_cookie
  if toggle:
    cookie_name = toggle+"-state"
%>

% if toggle:
<script>
    function toggle_${toggle}() {
        var button = $("#${toggle}-button");
        var div = $("#${toggle}");
        var active = button.text().trim() === 'Hide';
        button.text(active ? 'Show' : 'Hide');
        div.slideToggle(150);
        $.cookie('${cookie_name}', button.text().trim(), {expires : 3650});
    }
</script>
% endif


<h4>
% if toggle:
    <button id="${toggle}-button" class="btn btn-sm btn-light border" onclick="toggle_${toggle}()">
    ${'Hide' if get_cookie(request, cookie_name)=='Hide' else 'Show'}
    </button>
% endif
% if header is not None and count is not None:
  ${header} - ${count} tests
% elif header is not None:
  ${header}
% elif count is not None:
  ${count} tests
% endif
</h4>

<div
   id="${toggle}"
% if toggle:
   style="${'' if get_cookie(request, cookie_name)=='Hide' else 'display: none;'}"
% endif
>

  ${pagination()}

  <div class="table-responsive-lg">
    <table class="table table-striped table-sm run-table">
      <tbody>
        % for run in runs:
            <tr>
              % if show_delete:
                  <td style="width: 1%;" class="run-button run-deny">
                    <div class="dropdown">
                      <button type="submit" class="btn btn-danger btn-sm" data-bs-toggle="dropdown">
                        <i class="fas fa-trash-alt"></i>
                      </button>
                      <div class="dropdown-menu" role="menu">
                        <form action="/tests/delete" method="POST" style="display: inline;">
                          <input type="hidden" name="csrf_token"
                                 value="${request.session.get_csrf_token()}" />
                          <input type="hidden" name="run-id" value="${run['_id']}">
                          <button type="submit" class="btn btn-danger btn-mini">Confirm</button>
                        </form>
                      </div>
                    </div>
                  </td>

              % endif

              <td style="width: 6%;" class="run-date">
                ${run['start_time'].strftime("%y-%m-%d")}
              </td>

              <td style="width: 2%;" class="run-user">
                <a href="/tests/user/${run['args'].get('username', '')}"
                   title="${run['args'].get('username', '')}">
                  ${run['args'].get('username', '')[:3]}
                </a>
              </td>

              <td style="width: 16%;" class="run-view">
                <a href="/tests/view/${run['_id']}">${run['args']['new_tag'][:23]}</a>
              </td>

              <td style="width: 2%;" class="run-diff">
                <a href="${h.diff_url(run)}" target="_blank" rel="noopener">diff</a>
              </td>

              <td style="width: 1%;" class="run-elo">
                <%include file="elo_results.mak" args="run=run" />
              </td>

              <td style="width: 11%;" class="run-live">
                % if 'sprt' in run['args']:
                    <a href="/tests/live_elo/${str(run['_id'])}" target="_blank">sprt</a>
                % else:
                  ${run['args']['num_games']}
                % endif
                @ ${run['args']['tc']} th ${str(run['args'].get('threads',1))}
                <br>
                ${('cores: '+str(run['cores'])) if not run['finished'] and 'cores' in run else ''}
              </td>

              <td class="run-info">
                ${run['args'].get('info', '')}
              </td>
            </tr>
        % endfor
        % if alt and count == 0:
          <tr>
            <td> ${alt} </td>
          </tr>
        % endif
      </tbody>
    </table>
  </div>

  ${pagination()}
</div>
