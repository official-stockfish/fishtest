<%inherit file="base.mak"/>

<% re_run = len(args) > 0 %>

<form class="form-horizontal" action="${request.url}" method="POST">
  <legend>Create New Test</legend>
  <div class="control-group">
    <label class="control-label">Test type:</label>
    <div class="controls">
      <select name="test_type">
        <option value="Standard">Standard</option>
        <option value="Regression">Regression</option>
      </select>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test branch:</label>
    <div class="controls">
      <input name="test-branch" value="${args.get('new_tag', '')}" ${'readonly' if re_run else ''}>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test options:</label>
    <div class="controls">
    <input name="new-options" value="${args.get('new_options', 'Hash=128 OwnBook=false')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test signature:</label>
    <div class="controls">
      <input name="test-signature" value="${args.get('new_signature', '')}" ${'readonly' if re_run else ''}>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Base branch:</label>
    <div class="controls">
      <input name="base-branch" value="${args.get('base_tag', 'master')}" ${'readonly' if re_run else ''}>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Base options:</label>
    <div class="controls">
    <input name="base-options" value="${args.get('base_options', 'Hash=128 OwnBook=false')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Base signature:</label>
    <div class="controls">
      <input name="base-signature" value="${args.get('base_signature', '')}" ${'readonly' if re_run else ''}>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Stop rule:</label>
    <div class="controls">
      <select name="stop_rule">
        <option value="sprt">SPRT</option>
        <option value="numgames">NumGames</option>
        <option value="spsa">SPSA</option>
      </select>
      <div class="btn-group">
        <div class="btn" id="fast_test">Fast</div>
        <div class="btn" id="slow_test">Slow</div>
      </div>
    </div>
  </div>
  <div class="control-group stop_rule numgames">
    <label class="control-label">Number of games:</label>
    <div class="controls">
      <input name="num-games" value="${args.get('num_games', 20000)}">
    </div>
  </div>
  <div class="control-group stop_rule sprt">
    <label class="control-label">SPRT Elo0:</label>
    <div class="controls">
      <input name="sprt_elo0" value="${args.get('sprt', {'elo0': -1.5})['elo0']}">
    </div>
  </div>
  <div class="control-group stop_rule sprt">
    <label class="control-label">SPRT Elo1:</label>
    <div class="controls">
      <input name="sprt_elo1" value="${args.get('sprt', {'elo1': 4.5})['elo1']}">
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA parameters:</label>
    <div class="controls">
    <input name="spsa-params" value="${args.get('spsa', {'params': 'p1[-10 10] p2[0, 100]'})['params']}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Time Control:</label>
    <div class="controls">
      <input name="tc" value="${args.get('tc', '15+0.05')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Threads:</label>
    <div class="controls">
      <input name="threads" value="${args.get('threads', 1)}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Book:</label>
    <div class="controls">
      <input name="book" value="${args.get('book', '8moves_v3.pgn')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Book Depth:</label>
    <div class="controls">
      <input name="book-depth" value="${args.get('book_depth', 8)}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Priority:</label>
    <div class="controls">
      <input name="priority" value="${args.get('priority', 0)}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test Repo:</label>
    <div class="controls">
      <input name="tests-repo" value="${args.get('tests_repo', tests_repo)}" ${'readonly' if re_run else ''}>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Notes:</label>
    <div class="controls">
      <textarea name="run-info" class="span4">${args.get('info', '')}</textarea>
    </div>
  </div>

  %if 'resolved_base' in args:
    <input type="hidden" name="resolved_base" value="${args['resolved_base']}">
    <input type="hidden" name="resolved_new" value="${args['resolved_new']}">
    <input type="hidden" name="msg_base" value="${args.get('msg_base', '')}">
    <input type="hidden" name="msg_new" value="${args.get('msg_new', '')}">
  %endif

  <div class="control-group">
    <div class="controls">
      <button type="submit" class="btn btn-primary">Submit</button>
    </div>
  </div>
</form>

<script type="text/javascript">
$(function() {
  var update_sprt = function() {
    $('.stop_rule').show();
    var stop_rule = $('select[name=stop_rule]').val();
    if (stop_rule != 'numgames') $('.numgames').hide();
    if (stop_rule != 'sprt') $('.sprt').hide();
    if (stop_rule != 'spsa') $('.spsa').hide();
  };

  update_sprt();
  $('select[name=stop_rule]').change(update_sprt);

  $('#fast_test').click(function() {
    $('input[name=sprt_elo0]').val('-1.5');
    $('input[name=sprt_elo1]').val('4.5');
    $('input[name=tc]').val('15+0.05');
  });

  $('#slow_test').click(function() {
    $('input[name=sprt_elo0]').val('0.0');
    $('input[name=sprt_elo1]').val('6.0');
    $('input[name=tc]').val('60+0.05');
  });
});
</script>
