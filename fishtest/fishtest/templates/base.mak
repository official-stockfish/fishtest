<!DOCTYPE html>
<html>
<head>
  <title>Stockfish Testing Framework</title>
  <link href="/css/bootstrap.min.css" rel="stylesheet">

  <script src="http://code.jquery.com/jquery-1.8.3.js"></script>
  <script src="/js/bootstrap.min.js"></script>
  <script src="/js/jquery.cookie.js"></script>

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
          <li class="nav-header">Tests</li>
          <li><a href="/tests">Overview</a></li>
          <li><a href="/tests/run">New</a></li>
          <li class="nav-header">Misc</li>
          <li><a href="/users">Users</a></li>
          <li><a href="/actions">Actions</a></li>
          <li><a href="https://github.com/glinscott/fishtest/wiki" target="_blank">Help</a></li>
          <li><a href="http://chatwing.com/stockfish" target="_blank">Chat</a></li>
          <li class="nav-header">Links</li>
          <li><a href="https://github.com/glinscott/fishtest" target="_blank">Github</a></li>
          <li><a href="https://groups.google.com/forum/?fromgroups=#!forum/fishcooking" target="_blank">Forum</a></li>
          <li><a href="https://groups.google.com/forum/?fromgroups=#!forum/fishcooking_results" target="_blank">History</a></li>
          <li><a href="/regression">Regression</a></li>
          <!--<li><a href="http://bit.ly/11QsIkd" target="_blank">Regression</a></li>-->
          <li><a href="http://abrok.eu/stockfish/" target="_blank">Compiles</a></li>
          <li><a href="https://github.com/official-stockfish/Stockfish" target="_blank">SF-github</a></li>          
          <li class="nav-header">Admin</li>
          <li><a href="/signup">Register</a></li>
        </ul>
      </div>
      <div class="span11">
        ${self.flash_messages()}
        ${self.body()}
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

<%def name="repo(run)">${run['args'].get('tests_repo', 'https://github.com/mcostalba/FishCooking')}</%def>

<%def name="format_sha(branch, sha, run)">
  <a href="${repo(run)}/commit/${sha}" target="_blank">${branch}</a>
</%def>

<%def name="diff_url(run)">
  <a href="${repo(run)}/compare/${run['args']['resolved_base'][:7]}...${run['args']['resolved_new'][:7]}" target="_blank">diff</a>
</%def>
