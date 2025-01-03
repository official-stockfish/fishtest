<%page args="runs, pages=None, show_delete=False, header=None, count=None, toggle=None, alt=None, title=''"/>

<%namespace name="base" file="base.mak"/>

<%!
  from fishtest.util import get_cookie, is_active_sprt_ltc
%>
<%
  if toggle:
    cookie_name = toggle + "_state"
%>

% if toggle is None:
  <script>
    document.title =
      '${username + " - " if username else ""}Finished Tests${title} - page ${page_idx+1} | Stockfish Testing';
  </script>
% endif

% if toggle:
  <script>
    function toggle${toggle.capitalize()}() {
      const button = document.getElementById("${toggle}-button");
      const active = button.textContent.trim() === "Hide";
      button.textContent = active ? "Show" : "Hide";
      document.cookie =
        "${cookie_name}" + "=" + button.textContent.trim() + "; max-age=${60 * 60 * 24 * 365 * 10}; SameSite=Lax";
    }
  </script>
% endif

<h4>
% if toggle:
  <a id="${toggle}-button" class="btn btn-sm btn-light border"
     data-bs-toggle="collapse"
     href="#${toggle}"
     role="button"
     aria-expanded=${'true' if get_cookie(request, cookie_name)=='Hide' else 'false'}
     aria-controls="${toggle}" onclick="toggle${toggle.capitalize()}()">
  ${'Hide' if get_cookie(request, cookie_name)=='Hide' else 'Show'}
  </a>
% endif
% if header is not None and count is not None:
  ${header} - ${count} tests
% elif header is not None:
  ${header}
% elif count is not None:
  ${count} tests
% endif
</h4>

<section
  id="${toggle}"
% if toggle:
  class="${'collapse show' if get_cookie(request, cookie_name)=='Hide' else 'collapse'}"
% endif
>

  <%include file="pagination.mak" args="pages=pages"/>

  <div class="table-responsive-lg">
    <table class="table table-striped table-sm run-table" aria-labelledby="run-table-heading" role="presentation">
      <thead></thead>
      <tbody>
        % for run in runs:
          <tr>
            % if show_delete:
              <td style="width: 1%;" class="run-button run-deny">
                <div class="dropdown">
                  <button type="button" class="btn btn-danger btn-sm" data-bs-toggle="dropdown">
                    <i class="fas fa-trash-alt" title="Delete run" aria-label="Delete run"></i>
                  </button>
                  <div class="dropdown-menu" role="menu">
                    <form
                      action="/tests/delete"
                      method="POST"
                      style="display: inline;"
                      onsubmit="handleStopDeleteButton('${run['_id']}'); return true;"
                    >
                      <input type="hidden" name="csrf_token" value="${request.session.get_csrf_token()}">
                      <input type="hidden" name="run-id" value="${run['_id']}">
                      <button type="submit" class="btn btn-danger btn-mini">Confirm</button>
                    </form>
                  </div>
                </div>
              </td>
            % endif

            <td style="width: 6%;" class="run-date">
              <time
                datetime="${run['start_time'].strftime('%Y-%m-%dT%H:%M:%SZ')}"
                title="The starting date of the run" aria-label="The starting date of the run"
              >
                ${run['start_time'].strftime('%y-%m-%d')}
              </time>
            </td>

            <td style="width: 2%;" class="run-user">
              <a href="/tests/user/${run['args'].get('username', '')}"
                 title="View tests of user ${run['args'].get('username', '')}"
                 aria-label="View tests of user ${run['args'].get('username', '')}"
              >
                ${run['args'].get('username', '')[:3]}
              </a>
            </td>
            % if not run["finished"]:
              <td class="run-notification" style="width:3em;text-align:center;">
                <div
                  id="notification_${run['_id']}"
                  class="notifications"
                  onclick="handleNotification(this)"
                  style="display:inline-block;cursor:pointer;"
                  role="button"
                  title="Notification for ${run['_id']}"
                  aria-label="Notification for ${run['_id']}"
                >
                </div>
                <script>
                  setNotificationStatus_("${run['_id']}");   // no broadcast since this is at initialization
                </script>
              </td>
            % endif
            <td style="width: 16%;" class="run-view">
              <a
                href="/tests/view/${run['_id']}"
                aria-label="View test for ${run['args']['new_tag']}"
                title="View test for ${run['args']['new_tag']}"
              >${run['args']['new_tag'][:23]}</a>
            </td>

            <td style="width: 2%;" class="run-diff">
              <a
                href="${h.diff_url(run)}"
                target="_blank"
                rel="noopener"
                title="View diff for ${run['args']['new_tag']} on GitHub"
                aria-label="View diff for ${run['args']['new_tag']} on GitHub"
              >diff</a>
            </td>

            <td style="width: 1%;" class="run-elo">
              <%include file="elo_results.mak" args="run=run" />
            </td>

            <td style="width: 13%;" class="run-live">
              <span class="${'rounded ltc-highlight me-1' if is_active_sprt_ltc(run) else 'me-1'}">
              % if 'sprt' in run['args']:
                <a
                  href="/tests/live_elo/${str(run['_id'])}"
                  target="_blank"
                  title="View live Elo for ${run['args']['new_tag']}"
                  aria-label="View live Elo for ${run['args']['new_tag']}"
                >sprt</a>
              % else:
                <span
                  title="Number of games"
                  aria-label="Number of games"
                >${run['args']['num_games']}</span>
              % endif
              <span
                title="Time Control"
                aria-label="Time Control"
              >@ ${run['args']['tc']}&nbsp;</span>
              <span
                title="Threads for a side per game"
                aria-label="Threads for a side per game"
              >th&nbsp;${str(run['args'].get('threads',1))}</span>
              </span>
              % if not run['finished']:
                <div>
                  <span
                  title="Cores running test"
                  aria-label="Cores running test"
                  >cores:&nbsp;${run.get('cores', '')}&nbsp;</span>
                  <span
                    title="Workers running test"
                    aria-label="Workers running test"
                  >(${run.get('workers', '')})</span>
                </div>
              % endif
            </td>

            <td class="run-info">
              ${run['args'].get('info', '')}
            </td>
          </tr>
        % endfor
        % if alt and count == 0:
          <tr>
            <td colspan="8">${alt}</td>
          </tr>
        % endif
      </tbody>
    </table>
  </div>
  <%include file="pagination.mak" args="pages=pages"/>
</section>
