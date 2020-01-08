<%inherit file="base.mak"/>

<% re_run = len(args) > 0 %>

<form class="form-horizontal" action="${request.url}" method="POST">
  <legend>Create New Test</legend>
  Please read the <a href="https://github.com/glinscott/fishtest/wiki/Creating-my-first-test">Testing Guidelines</a> before
  creating your test.

  <br><br>
  <div class="control-group">
    <label class="control-label">Test branch:</label>
    <div class="controls">
      <input name="test-branch" value="${args.get('new_tag', '')}" ${'readonly' if re_run else ''}>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test options:</label>
    <div class="controls">
    <input name="new-options" value="${args.get('new_options', 'Hash=16')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Test signature:</label>
    <div class="controls">
      <input name="test-signature" placeholder="Defaults to last commit message" value="${args.get('new_signature', '')}" ${'readonly' if re_run else ''}>
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
    <input name="base-options" value="${args.get('base_options', 'Hash=16')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Base signature:</label>
    <div class="controls">
      <input name="base-signature" value="${args.get('base_signature', bench)}" ${'readonly' if re_run else ''}>
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
    </div>
  </div>
  <div class="control-group stop_rule numgames spsa">
    <label class="control-label">Number of games:</label>
    <div class="controls">
      <input name="num-games" value="${args.get('num_games', 20000)}">
    </div>
  </div>
  <div class="control-group stop_rule sprt">
    <label class="control-label">SPRT bounds:</label>
    <div class="controls">
      <select name="bounds">
        <option value="standard STC">Standard STC {-1,3}</option>
        <option value="standard LTC">Standard LTC {0,2}</option>
        <option value="regression">Non-regression {-1.5,0.5}</option>
        <option value="simplification">Simplification {-1.5,0.5}</option>
        <option value="custom">Custom bounds...</option>
      </select>
    </div>
  </div>
  <div class="control-group stop_rule sprt custom_bounds">
    <label class="control-label">SPRT Elo0:</label>
    <div class="controls">
      <input name="sprt_elo0" value="${args.get('sprt', {'elo0': 0})['elo0']}">
    </div>
  </div>
  <div class="control-group stop_rule sprt custom_bounds">
    <label class="control-label">SPRT Elo1:</label>
    <div class="controls">
      <input name="sprt_elo1" value="${args.get('sprt', {'elo1': 5})['elo1']}">
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA A:</label>
    <div class="controls">
			<input name="spsa_A" value="${args.get('spsa', {'A': 5000})['A']}">
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA Gamma:</label>
    <div class="controls">
			<input name="spsa_gamma" value="${args.get('spsa', {'gamma': 0.101})['gamma']}">
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA Alpha:</label>
    <div class="controls">
			<input name="spsa_alpha" value="${args.get('spsa', {'alpha': 0.602})['alpha']}">
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA parameters:</label>
    <div class="controls">
      <textarea name="spsa_raw_params" class="span6">${args.get('spsa', {'raw_params': """Aggressiveness,30,0,200,10,0.0020
Cowardice,150,0,200,10,0.0020"""})['raw_params']}</textarea>
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA clipping:</label>
    <div class="controls">
      <select name="spsa_clipping">
        <option value="old">old</option>
        <option value="careful">careful</option>
      </select>
    </div>
  </div>
  <div class="control-group stop_rule spsa">
    <label class="control-label">SPSA rounding:</label>
    <div class="controls">
      <select name="spsa_rounding">
        <option value="deterministic">deterministic</option>
        <option value="randomized">randomized</option>
      </select>
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Time Control:</label>
    <div class="controls">
      <input name="tc" value="${args.get('tc', '10+0.1')}">
      <div class="btn-group">
        <div class="btn" id="fast_test">short (STC)</div>
        <div class="btn" id="slow_test">long (LTC)</div>
      </div>
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
      <input name="book" value="${args.get('book', 'noob_3moves.epd')}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Book Depth:</label>
    <div class="controls">
      <input name="book-depth" value="${args.get('book_depth', 8)}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Advanced:</label>
    <div class="controls checkbox inline">
      <input name="auto-purge" type="checkbox" checked="checked" value="True">Auto-purge
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Priority:</label>
    <div class="controls">
      <input name="priority" value="${args.get('priority', 0)}">
    </div>
  </div>
  <div class="control-group">
    <label class="control-label">Throughput%:</label>
    <div class="controls">
      <select name="throughput">
        <option value="10">10%</option>
        <option value="25">25%</option>
        <option value="50">50%</option>
        <option selected="selected" value="100">100%</option>
        <option style="color:red" value="200">200%</option>
      </select>
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
      <textarea name="run-info" class="span4" placeholder="Defaults to commit message">${args.get('info', '')}</textarea>
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
  var update_bounds = function() {
    var bounds = $('select[name=bounds]').val();
    if (bounds == 'standard STC') { $('input[name=sprt_elo0]').val('-1.0'); $('input[name=sprt_elo1]').val('3.0'); }
    if (bounds == 'standard LTC') { $('input[name=sprt_elo0]').val('0.0'); $('input[name=sprt_elo1]').val('2.0'); }
    if (bounds == 'regression') { $('input[name=sprt_elo0]').val('-1.5'); $('input[name=sprt_elo1]').val('0.5'); }
    if (bounds == 'simplification') { $('input[name=sprt_elo0]').val('-1.5'); $('input[name=sprt_elo1]').val('0.5'); }
    if (bounds == 'custom')
      $('.custom_bounds').show();
    else
      $('.custom_bounds').hide();
  };
  var update_visibility = function() {
    $('.stop_rule').hide();
    var stop_rule = $('select[name=stop_rule]').val();
    if (stop_rule == 'numgames') $('.numgames').show();
    if (stop_rule == 'sprt') { $('.sprt').show(); update_bounds(); }
    if (stop_rule == 'spsa') $('.spsa').show();
  };

  $('select[name=bounds]').val("${'custom' if re_run else 'standard'}");
  update_visibility();
  $('select[name=stop_rule]').change(update_visibility);
  $('select[name=bounds]').change(update_bounds);

  $('#fast_test').click(function() {
    $('input[name=tc]').val('10+0.1');
    $('input[name=new-options]').val('Hash=16');
    $('input[name=base-options]').val('Hash=16');
    if ($('input[name=sprt_elo0]').val() == '0.0' && $('input[name=sprt_elo1]').val() == '2.0')
      { $('select[name=bounds]').val('standard STC'); update_bounds(); }
  });

  $('#slow_test').click(function() {
    $('input[name=tc]').val('60+0.6');
    $('input[name=new-options]').val('Hash=64');
    $('input[name=base-options]').val('Hash=64');
    if ($('input[name=sprt_elo0]').val() == '-1.0' && $('input[name=sprt_elo1]').val() == '3.0')
      { $('select[name=bounds]').val('standard LTC'); update_bounds(); }
  });
});
</script>
