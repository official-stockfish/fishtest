<%inherit file="base.mak"/>

<script type="text/javascript" src="https://www.google.com/jsapi"></script>
<script type="text/javascript" >
  function decode(input) {
    var e = document.createElement('div');
    e.innerHTML = input;
    return e.childNodes.length === 0 ? "" : e.childNodes[0].nodeValue;
  }
  var fishtest_data = $.parseJSON(decode("${fishtest_regression_data}"));
  var jl_data = $.parseJSON(decode("${jl_regression_data}"));
</script>
<script type="text/javascript" src="/js/regression.js"></script>

<h3>Testing for software regression</h3>

<h4>Fishtest regression tests against Stockfish 5</h4>

<div>
<a href="/regression/data?type=fishtest" class="btn btn-default" role="button">Update Data</a>
</div>

<div id="fishtest_graph" style="width: 900px; height: 600px;"></div>

<h4>Tournament regression tests carried out by Jens Lehmann</h4>

<div class="btn-group">
  <button class="btn btn-default dropdown-toggle" data-toggle="dropdown" id=
  "btn_select_jl_test" type="button"><span id=
  "btn_select_jl_test_caption">Select Run</span>&nbsp;<span class=
  "caret"></span></button>

  <ul class="dropdown-menu" id="dropdown_jl_tests"></ul>
  <div class="btn-group" role="group" style="margin-left: 10px;">
    <a href="/regression/data?type=jl" class="btn btn-default" role="button">Update Data</a>
  </div>
</div>

<div style="padding: 5px;">
  Number of games played per engine: <span id="jl_games_count"></span>
</div>

<div id="jl_graph" style="width: 900px; height: 600px;"></div>

<h4>Link to old results</h4>

<div style="margin-bottom: 70px;">
  <a href="http://bit.ly/11QsIkd" target="_blank">http://bit.ly/11QsIkd</a>
</div>
