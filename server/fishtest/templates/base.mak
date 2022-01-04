<%
  monitoring = request.rundb.conn["admin"].command("getFreeMonitoringStatus")
%>
<!DOCTYPE html>
<html>
  <head>
    <title>Stockfish Testing Framework</title>
    <meta name="csrf-token" content="${request.session.get_csrf_token()}" />
    <meta name="dark-theme-sha256" content="${cache_busters['css/theme.dark.css']}" />

    <link rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
          integrity="sha512-1ycn6IcaQQ40/MKBW2W4Rhis/DbILU74C1vSrLJxCq57o941Ym01SwNsOMqvEBFlcgUa6xLiPY/NS5R+E6ztJQ=="
          crossorigin="anonymous"
          referrerpolicy="no-referrer" />

    <link rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.1/dist/css/bootstrap.min.css"
          integrity="sha384-F3w7mX95PdgyTmZZMECAngseQB83DfGTowi0iMjiWaeVhAn4FJkqJByhZMI3AhiU"
          crossorigin="anonymous">

    <link href="/css/application.css?v=${cache_busters['css/application.css']}" rel="stylesheet">
    % if request.cookies.get('theme') == 'dark':
        <link href="/css/theme.dark.css?v=${cache_busters['css/theme.dark.css']}" rel="stylesheet">
    % endif

    <script src="https://code.jquery.com/jquery-3.5.1.min.js"
            integrity="sha256-9/aliU8dGd2tb6OSsuzixeV4y/faTqgFtohetphbbj0="
            crossorigin="anonymous"></script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.1/dist/js/bootstrap.bundle.min.js"
            integrity="sha384-/bQdsTh/da6pkI1MST/rWKFNjaCP5gBSY4sEBT38Q/9RBh9AH40zEOg7Hlq2THRZ"
            crossorigin="anonymous"></script>

    <script src="/js/jquery.cookie.js" defer></script>
    <script src="/js/application.js?v=${cache_busters['js/application.js']}" defer></script>

    <%block name="head"/>
  </head>

  <body>
    <div class="clearfix mainnavbar">
      <ul class="nav nav-list flex-column">

        <li class="nav-header">Tests</li>
        <li><a href="/tests">Overview</a></li>
        <li><a href="/tests/run">New Test</a></li>
        % if request.authenticated_userid:
            <li><a href="/tests/user/${request.authenticated_userid}">My Tests</a></li>
        % endif
        <li><a href="/tests/finished?ltc_only=1">LTC</a></li>
        <li><a href="/tests/finished?success_only=1">Greens</a></li>
        <li><a href="/tests/finished?yellow_only=1">Yellows</a></li>
        <li><a href="https://groups.google.com/g/fishcooking-results" target="_blank" rel="noopener">History</a></li>
        % if request.authenticated_userid:
            <li><a href="/upload">NN Upload</a></li>
        % endif

        <li class="nav-header">Fishtest</li>
        <li><a href="/users">Contributors</a></li>
        <li><a href="/users/monthly">Top Month</a></li>
        <li><a href="/actions">Events</a></li>
%if monitoring["state"] == 'enabled':
       <li><a href=${monitoring["url"]} target="_blank" rel="noopener">Monitoring</a></li>
%endif
        <li>
          % if len(request.userdb.get_pending()) > 0:
              <a href="/pending"
                 style="color: var(--bs-danger);">Pending (${len(request.userdb.get_pending())})</a>
          % else:
              <a href="/pending">Pending</a>
          % endif
        </li>
        % if request.authenticated_userid:
            <li><a href="/user">My Profile</a></li>
            <li><a href="/logout" id="logout">Logout</a></li>
        % else:
            <li><a href="/signup">Register</a></li>
            <li><a href="/login">Login</a></li>
        % endif
        <li id="change-color-theme">
          <div id="sun" style="${'display: none;' if request.cookies.get('theme') != 'dark' else ''}">Light Mode</div>
          <div id="moon" style="${'display: none;' if request.cookies.get('theme') == 'dark' else ''}">Dark Mode</div>
        </li>

        <li class="nav-header">Stockfish</li>
        <li><a href="https://stockfishchess.org/download/" target="_blank" rel="noopener">Official Releases</a></li>
        <li><a href="https://abrok.eu/stockfish/" target="_blank" rel="noopener">Dev Builds</a></li>
        <li><a href="https://stockfishchess.org/get-involved/" target="_blank" rel="noopener">Contribute</a></li>
        <li><a href="https://github.com/glinscott/fishtest/wiki/Regression-Tests" target="_blank" rel="noopener">Progress</a></li>
        <li><a href="/nns">NN Repo</a></li>

        <li class="nav-header">Resources</li>
        <li><a href="https://discord.gg/nv8gDtt" target="_blank" rel="noopener">Discord</a></li>
        <li><a href="https://groups.google.com/g/fishcooking" target="_blank" rel="noopener">Forum</a></li>
        <li><a href="https://github.com/glinscott/fishtest/wiki" target="_blank" rel="noopener">Wiki</a></li>
        <li><a href="/html/SPRTcalculator.html?elo-model=Normalized&elo-0=0.0&elo-1=2.5&draw-ratio=0.49&rms-bias=191" target="_blank">SPRT Calc</a></li>
        <li><a href="https://hxim.github.io/Stockfish-Evaluation-Guide/" target="_blank" rel="noopener">Eval Guide</a></li>

        <li class="nav-header">Development</li>
        <li><a href="https://github.com/official-stockfish/Stockfish" target="_blank" rel="noopener">Stockfish</a></li>
        <li><a href="https://github.com/glinscott/fishtest" target="_blank" rel="noopener">Fishtest</a></li>
        <li><a href="https://github.com/glinscott/nnue-pytorch" target="_blank" rel="noopener">NN Trainer</a></li>
        <li><a href="https://github.com/official-stockfish/books" target="_blank" rel="noopener">Books</a></li>

      </ul>
    </div>

    <div class="clearfix contentbase">
      <div class="container-fluid">
        <div class="row-fluid">
          <div class="flash-message">
            % if request.session.peek_flash('error'):
                <% flash = request.session.pop_flash('error') %>
                % for message in flash:
                    <div class="alert alert-danger alert-dismissible">
                      ${message}
                      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close">
                      </button>
                    </div>
                % endfor
            % endif
            % if request.session.peek_flash():
                <% flash = request.session.pop_flash() %>
                % for message in flash:
                    <div class="alert alert-success alert-dismissible">
                      ${message}
                      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close">
                      </button>
                    </div>
                % endfor
            % endif
          </div>
          <main>${self.body()}</main>
        </div>
      </div>
    </div>
  </body>

  <script>
    (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
    (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
    m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
    })(window,document,'script','//www.google-analytics.com/analytics.js','ga');

    ga('create', 'UA-41961447-1', 'stockfishchess.org');
    ga('send', 'pageview');
  </script>
</html>
