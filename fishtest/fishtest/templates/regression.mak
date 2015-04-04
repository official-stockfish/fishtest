<%inherit file="base.mak"/>

<style type="text/css">
  .table_standings, {
    border-collapse: collapse;
    margin-top: 20px;
  }

  .table_standings td, th{
    border: 1px solid #ddd;
    padding: 10px 10px;

  }

  .table_standings td:last-child a{
    margin-top: -42px;
  }
</style>

<script type="text/javascript" src="https://www.google.com/jsapi"></script>

<script type="text/javascript" src="/js/regression.js"></script>

<h3>Testing for software regression</h3>

<h4>Regression tests against latest release</h4>

<div>
<a href="/regression/data?type=fishtest" class="btn btn-default" role="button">Update Data</a>
</div>

<div id="fishtest_graph" style="width: 900px; height: 600px;"></div>
<div>
<table class="table_standings" id="table_standings_fishtest">
      <thead><tr>
        <th>Commit SHA</th>
        <th>Test Details</th>
        <th>Elo</th>
        <th>Change</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>
      </table>
</div>

<h4 style="margin-top: 70px; margin-bottom: 20px;">Tournament regression tests carried out by Jens Lehmann</h4>

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
  <div style="position: absolute; top: 0; left: 0; width: 900px;">
    <div id="jl_graph" style="width: 900px; height: 600px;"></div>
    <div>
      <table class="table_standings" id="table_standings_jl">
      <thead><tr>
        <th>Date Committed</th>
        <th>Commit SHA</th>
        <th>Elo</th>
        <th>Change</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>
      </table>
    </div>

    <div style="margin-bottom: 70px; margin-top: 100px;">
      <h4>Link to old results</h4>
      <a href="http://bit.ly/11QsIkd" target="_blank">http://bit.ly/11QsIkd</a>
    </div>
  </div>

  <div style="position: absolute; top: 0; left: 900px; padding: 5px;">
    <div><b>Description:</b></div>
    <div style="width: 300px;" id="description"></div>
    <div style="padding-top: 30px;"><b>Date</b></div>
    <div id="date"></div>
  </div>
</div>


