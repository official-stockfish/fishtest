<!DOCTYPE html>
<html>
<head>
  <title>Stockfish Testing Framework</title>
  <link href="/css/bootstrap.min.css" rel="stylesheet">

  <script src="http://code.jquery.com/jquery-1.8.3.js"></script>

  <style>
    .elo-results {
      font-size:12px;
      margin:2px;
      padding:1px;
      line-height:13px
    }
  </style>

  ${self.head()}
</head>
<body>
  <div class="container-fluid">
    <div class="row-fluid">
      <div class="span1">
        <ul class="nav nav-list">
          <li><a href="/signup">Sign up</a></li>
          <li class="nav-header">Tests</li>
          <li><a href="/tests">Overview</a></li>
          <li><a href="/tests/run">New</a></li>
          <li class="nav-header">Misc</li>
          <li><a href="/">Login</a></li>
          <li><a href="/users">Users</a></li>
        </ul>
      </div>
      <div class="span11">
        ${self.flash_messages()}
        ${self.body()}
      </div>
    </div>
  </div>

  <script src="/js/bootstrap.min.js"></script>
</body>
</html>

<%def name="flash_messages()">
  %if request.session.peek_flash():
    <% flash = request.session.pop_flash() %>
    %for message in flash:
      <div class="alert alert-success">
        <button type="button" class="close" data-dismiss="alert">x</button>
        ${message}
      </div>
    %endfor
  %endif
</%def>

<%def name="head()">
</%def>

<%def name="repo()">https://github.com/mcostalba/FishCooking</%def>

<%def name="format_sha(sha)">
  <a href="${repo()}/commit/${sha}">${sha[:7]}</a>
</%def>

<%def name="diff_url(run, title='diff')">
  <a href="${repo()}/compare/${run['args']['resolved_base'][:7]}...${run['args']['resolved_new'][:7]}">${title}</a>
</%def>
