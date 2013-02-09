<!DOCTYPE html>
<html>
<head>
  <title>Stockfish Testing</title>
  <link href="/css/bootstrap.min.css" rel="stylesheet">

  <script src="http://code.jquery.com/jquery-1.8.3.js"></script>

  ${self.head()}
</head>
<body>
  <div class="container-fluid">
    <div class="row-fluid">
      <div class="span2">
        <ul class="nav nav-list">
          <li class="nav-header">Tests</li>
          <li><a href="/tests">Tests Overview</a></li>
          <li><a href="/tests/run">Run Test!</a></li>
        </ul>
      </div>
      <div class="span10">
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
