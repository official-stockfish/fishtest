<%
  monitoring = request.rundb.conn["admin"].command("getFreeMonitoringStatus")
%>
<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Stockfish Testing Framework</title>
    <meta name="csrf-token" content="${request.session.get_csrf_token()}" />
    <meta name="dark-theme-sha256" content="${cache_busters['css/theme.dark.css']}" />

    <link rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.1.1/css/all.min.css"
          integrity="sha512-KfkfwYDsLkIlwQp6LFnl8zNdLGxu9YAA1QvwINks4PhcElQSvqcyVLLD9aMhXd13uQjoXtEKNosOWaZqXgel0g=="
          crossorigin="anonymous"
          referrerpolicy="no-referrer" />

    <link rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/css/bootstrap.min.css"
          integrity="sha512-GQGU0fMMi238uA+a/bdWJfpUGKUkBdgfFdgBm72SUQ6BeyWjoY/ton0tEjH+OSH9iP4Dfh+7HM0I9f5eR0L/4w=="
          crossorigin="anonymous"
          referrerpolicy="no-referrer" />

    <link href="/css/application.css?v=${cache_busters['css/application.css']}" rel="stylesheet">
    % if request.cookies.get('theme') == 'dark':
        <link href="/css/theme.dark.css?v=${cache_busters['css/theme.dark.css']}" rel="stylesheet">
    % endif

    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js"
            integrity="sha512-894YE6QWD5I59HgZOGReFYm4dnWc1Qt5NtvYSaNcOP+u1T9qYdvdihz0PPSiiqn/+/3e7Jo4EaG7TubfWGUrMQ=="
            crossorigin="anonymous"
            referrerpolicy="no-referrer"></script>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/js/bootstrap.bundle.min.js"
            integrity="sha512-pax4MlgXjHEPfCwcJLQhigY7+N8rt6bVvWLFyUMuxShv170X53TRzGPmPkZmGBhk+jikR8WBM4yl7A9WMHHqvg=="
            crossorigin="anonymous"
            referrerpolicy="no-referrer"></script>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery-cookie/1.4.1/jquery.cookie.min.js"
            integrity="sha512-3j3VU6WC5rPQB4Ld1jnLV7Kd5xr+cq9avvhwqzbH/taCRNURoeEpoPBK9pDyeukwSxwRPJ8fDgvYXd6SkaZ2TA=="
            crossorigin="anonymous"
            referrerpolicy="no-referrer"></script>

    <script src="/js/application.js?v=${cache_busters['js/application.js']}" defer></script>

    <%block name="head"/>
  </head>

  <body>
    <div class="mainnavbar user-select-none vh-100 pt-2 pt-md-3 overflow-auto">
      <ul class="nav nav-list flex-column mb-2 px-1">

        <li class="nav-header mb-1 pt-1 ps-2">Tests</li>
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

        <li class="nav-header my-1 pt-1 ps-2">Fishtest</li>
        <li><a href="/users">Contributors</a></li>
        <li><a href="/users/monthly">Top Month</a></li>
        <li><a href="/actions">Events</a></li>
        % if monitoring["state"] == 'enabled':
            <li><a href=${monitoring["url"]} target="_blank" rel="noopener">Monitoring</a></li>
        % endif
        <li>
          % if len(request.userdb.get_pending()) > 0:
              <a href="/pending"
                 style="color: var(--bs-danger);">Pending Users (${len(request.userdb.get_pending())})</a>
          % else:
              <a href="/pending">Pending Users</a>
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

        <li class="nav-header my-1 pt-1 ps-2">Stockfish</li>
        <li><a href="https://stockfishchess.org/download/" target="_blank" rel="noopener">Official Releases</a></li>
        <li><a href="https://abrok.eu/stockfish/" target="_blank" rel="noopener">Dev Builds</a></li>
        <li><a href="https://stockfishchess.org/get-involved/" target="_blank" rel="noopener">Contribute</a></li>
        <li><a href="https://github.com/glinscott/fishtest/wiki/Regression-Tests" target="_blank" rel="noopener">Progress</a></li>
        <li><a href="/nns">NN Repo</a></li>

        <li class="nav-header my-1 pt-1 ps-2">Resources</li>
        <li><a href="https://discord.gg/awnh2qZfTT" target="_blank" rel="noopener">Discord</a></li>
        <li><a href="https://groups.google.com/g/fishcooking" target="_blank" rel="noopener">Forum</a></li>
        <li><a href="https://github.com/glinscott/fishtest/wiki" target="_blank" rel="noopener">Wiki</a></li>
        <li><a href="/html/SPRTcalculator.html?elo-model=Normalized&elo-0=0.0&elo-1=2.5&draw-ratio=0.49&rms-bias=191&v=${cache_busters['html/SPRTcalculator.html']}" target="_blank">SPRT Calc</a></li>
        <li><a href="https://hxim.github.io/Stockfish-Evaluation-Guide/" target="_blank" rel="noopener">Eval Guide</a></li>

        <li class="nav-header my-1 pt-1 ps-2">Development</li>
        <li><a href="https://github.com/official-stockfish/Stockfish" target="_blank" rel="noopener">Stockfish</a></li>
        <li><a href="https://github.com/glinscott/fishtest" target="_blank" rel="noopener">Fishtest</a></li>
        <li><a href="https://github.com/glinscott/nnue-pytorch" target="_blank" rel="noopener">NN Trainer</a></li>
        <li><a href="https://github.com/official-stockfish/books" target="_blank" rel="noopener">Books</a></li>

      </ul>
    </div>

    <div class="contentbase vh-100 w-100">
      <div class="container-fluid pe-0">
        <div class="row">
          <div class="flash-message mt-3">
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
