<%inherit file="base.mak"/>

<script type="text/javascript" src="https://www.google.com/jsapi"></script>

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

<div style="position:relative;">
  <div id="jl_graph" style="position: absolute; top: 0; left: 0; width: 900px; height: 600px;"></div>
  <div style="position: absolute; top: 0; left: 900px; padding: 5px;">
    <div><b>Description:</b></div>
    <div style="width: 300px;" id="description"></div>
    <div style="padding-top: 30px;"><b>Date</b></div>
    <div id="date"></div>
  </div>
</div>

<h4>Link to old results</h4>

<div style="margin-bottom: 70px;">
  <a href="http://bit.ly/11QsIkd" target="_blank">http://bit.ly/11QsIkd</a>
</div>
