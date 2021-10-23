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
        <li><a href="/tests/finished?success_only=1">Greens</a></li>
        <li><a href="/tests/finished?yellow_only=1">Yellows</a></li>
        <li><a href="/tests/finished?ltc_only=1">LTC</a></li>
        % if request.authenticated_userid:
            <li><a href="/tests/user/${request.authenticated_userid}">My Tests</a></li>
        % endif
        <li><a href="/tests/run">New</a></li>
        % if request.authenticated_userid:
            <li><a href="/upload">NN Upload</a></li>
        % endif

        <li class="nav-header">Misc</li>
        <li><a href="/users">Users</a></li>
        <li><a href="/users/monthly">Top Month</a></li>
        <li><a href="/actions">Actions</a></li>
        <li><a href="/nns">NN Repo</a></li>
        <li><a href="/html/SPRTcalculator.html?elo-model=Normalized&elo-0=-0.5&elo-1=2.5&draw-ratio=0.49&rms-bias=191" target="_blank">SPRT Calc</a></li>

        <li class="nav-header">Github</li>
        <li><a href="https://github.com/glinscott/fishtest" target="_blank" rel="noopener">Fishtest</a></li>
        <li><a href="https://github.com/glinscott/nnue-pytorch" target="_blank" rel="noopener">NN Trainer</a></li>
        <li><a href="https://github.com/official-stockfish/books" target="_blank" rel="noopener">Books</a></li>
        <li><a href="https://github.com/official-stockfish/Stockfish" target="_blank" rel="noopener">Stockfish</a></li>

        <li class="nav-header">Links</li>
        <li><a href="https://github.com/glinscott/fishtest/wiki" target="_blank" rel="noopener">Wiki</a></li>
        <li><a href="https://groups.google.com/g/fishcooking" target="_blank" rel="noopener">Forum</a></li>
        <li><a href="https://groups.google.com/g/fishcooking-results" target="_blank" rel="noopener">History</a></li>
        <li><a href="https://hxim.github.io/Stockfish-Evaluation-Guide/" target="_blank" rel="noopener">Eval Guide</a></li>
        <li><a href="https://github.com/glinscott/fishtest/wiki/Regression-Tests" target="_blank" rel="noopener">Regression</a></li>
        <li><a href="https://abrok.eu/stockfish/" target="_blank" rel="noopener">Compiles</a></li>
        <li><a href="https://discord.gg/nv8gDtt" target="_blank" rel="noopener">Discord</a></li>

        <li class="nav-header">Admin</li>
        % if request.authenticated_userid:
            <li><a href="/user">Profile</a></li>
            <li><a href="/logout" id="logout">Logout</a></li>
        % else:
            <li><a href="/signup">Register</a></li>
            <li><a href="/login">Login</a></li>
        % endif
        <li>
          % if len(request.userdb.get_pending()) > 0:
              <a href="/pending"
                 style="color: var(--bs-danger);">Pending (${len(request.userdb.get_pending())})</a>
          % else:
              <a href="/pending">Pending</a>
          % endif
        </li>
        <li>
          <svg id="change-color-theme" viewBox="0 0 8 8" style="width: 20px; height: 20px; background: none;">
            <path id="sun" style="${'display: none;' if request.cookies.get('theme') != 'dark' else ''}"
                  d="M4 0c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm-2.5 1c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm5 0c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm-2.5 1c-1.105 0-2 .895-2 2s.895 2 2 2 2-.895 2-2-.895-2-2-2zm-3.5 1.5c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm7 0c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm-6 2.5c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm5 0c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5zm-2.5 1c-.276 0-.5.224-.5.5s.224.5.5.5.5-.224.5-.5-.224-.5-.5-.5z"></path>
            <path id="moon" style="${'display: none;' if request.cookies.get('theme') == 'dark' else ''}"
                  d="M2.719 0c-1.58.53-2.719 2.021-2.719 3.781 0 2.21 1.79 4 4 4 1.76 0 3.251-1.17 3.781-2.75-.4.14-.831.25-1.281.25-2.21 0-4-1.79-4-4 0-.44.079-.881.219-1.281z"></path>
          </svg>
        </li>
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
