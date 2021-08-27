<%
   import math,copy
   import fishtest.stats.stat_util
   import fishtest.stats.LLRcalc

   has_sprt        = 'sprt'        in run['args'].keys()
   has_pentanomial = 'pentanomial' in run['results'].keys()
   has_spsa        = 'spsa'        in run['args'].keys()

   def pdf_to_string(pdf,decimals=(2,5)):
      format="%."+str(decimals[0])+"f"+": "+"%."+str(decimals[1])+"f"
      return "{"+", ".join([(format % (value,prob)) for value,prob in pdf])+"}"

   def list_to_string(l,decimals=6):
       format="%."+str(decimals)+"f"
       return "["+", ".join([format % value for value in l])+"]"

   def t_conf(avg,var,skewness,exkurt):
      t=(avg-0.5)/var**.5
      var_t=1-t*skewness+0.25*t**2*(exkurt+2)
      if var_t<0: # in principle this cannot happen except (perhaps)
                  # for rounding errors
      	 var_t=0  
      return t,var_t

   z975=fishtest.stats.stat_util.Phi_inv(0.975)

   nelo_divided_by_nt=800/math.log(10)  ## 347.43558552260146 

   results3=[run['results']['losses'],run['results']['draws'],run['results']['wins']]
   results3_=fishtest.stats.LLRcalc.regularize(results3)
   draw_ratio=results3_[1]/float(sum(results3_))
   N3,pdf3=fishtest.stats.LLRcalc.results_to_pdf(results3)
   games3=N3
   avg3,var3,skewness3,exkurt3=fishtest.stats.LLRcalc.stats_ex(pdf3)
   stdev3=var3**.5
   games=games3
   sigma=stdev3
   pdf3_s=pdf_to_string(pdf3)
   avg3_l=avg3-z975*(var3/N3)**.5
   avg3_u=avg3+z975*(var3/N3)**.5
   var3_l=var3*(1-z975*((exkurt3+2)/N3)**.5)
   var3_u=var3*(1+z975*((exkurt3+2)/N3)**.5)
   stdev3_l=var3_l**.5 if var3_l>=0 else 0.0
   stdev3_u=var3_u**.5
   t3,var_t3=t_conf(avg3,var3,skewness3,exkurt3)
   t3_l=t3-z975*(var_t3/N3)**.5
   t3_u=t3+z975*(var_t3/N3)**.5
   nt3=t3
   nt3_l=t3_l
   nt3_u=t3_u
   nelo3=nelo_divided_by_nt*nt3
   nelo3_u=nelo_divided_by_nt*nt3_u
   nelo3_l=nelo_divided_by_nt*nt3_l
   if has_pentanomial:
      results5=run['results']['pentanomial']
      results5_=fishtest.stats.LLRcalc.regularize(results5)
      N5,pdf5=fishtest.stats.LLRcalc.results_to_pdf(results5)
      games5=2*N5
      avg5,var5,skewness5,exkurt5=fishtest.stats.LLRcalc.stats_ex(pdf5)
      var5_per_game=2*var5
      stdev5_per_game=var5_per_game**.5
      games=games5
      sigma=stdev5_per_game
      pdf5_s=pdf_to_string(pdf5)
      avg5_l=avg5-z975*(var5/N5)**.5
      avg5_u=avg5+z975*(var5/N5)**.5
      var5_per_game_l=var5_per_game*(1-z975*((exkurt5+2)/N5)**.5)
      var5_per_game_u=var5_per_game*(1+z975*((exkurt5+2)/N5)**.5)
      stdev5_per_game_l=var5_per_game_l**.5 if var5_per_game_l>=0 else 0.0
      stdev5_per_game_u=var5_per_game_u**.5
      t5,var_t5=t_conf(avg5,var5,skewness5,exkurt5)
      t5_l=t5-z975*(var_t5/N5)**.5
      t5_u=t5+z975*(var_t5/N5)**.5
      sqrt2=2**.5
      nt5=t5/sqrt2
      nt5_l=t5_l/sqrt2
      nt5_u=t5_u/sqrt2
      nelo5=nelo_divided_by_nt*nt5
      nelo5_u=nelo_divided_by_nt*nt5_u
      nelo5_l=nelo_divided_by_nt*nt5_l
      results5_DD_prob=draw_ratio-(results5_[1]+results5_[3])/(2*float(N5))
      results5_WL_prob=results5_[2]/float(N5)-results5_DD_prob
      R3_=copy.deepcopy(run['results'])
      del R3_['pentanomial']
      ratio=var5_per_game/var3
      var_diff=var3-var5_per_game
      RMS_bias=var_diff**.5 if var_diff>=0 else 0
      RMS_bias_elo=fishtest.stats.stat_util.elo(0.5+RMS_bias)

   drawelo=fishtest.stats.stat_util.draw_elo_calc(results3_)
   if has_sprt:
      elo_model=run['args']['sprt'].get('elo_model','BayesElo')
      alpha=run['args']['sprt']['alpha']
      beta=run['args']['sprt']['beta']
      elo0=run['args']['sprt']['elo0']
      elo1=run['args']['sprt']['elo1']
      batch_size_units=run['args']['sprt'].get('batch_size',1)
      batch_size_games=2*batch_size_units if has_pentanomial else 1
      o=run['args']['sprt'].get('overshoot',None)
      assert elo_model in ['BayesElo','logistic','normalized']
      belo0,belo1=None,None
      if elo_model=='BayesElo':
         belo0,belo1=elo0,elo1
      	 elo0_,elo1_=[fishtest.stats.stat_util.bayeselo_to_elo(belo_, drawelo) for belo_ in (belo0,belo1)]
	 elo_model_='logistic'
      else:
         elo0_,elo1_=elo0,elo1
         elo_model_=elo_model
      assert elo_model_ in ['logistic','normalized']
      if elo_model_=='logistic':
	 lelo03,lelo13=lelo0,lelo1=elo0_,elo1_
         score03,score13=score0,score1=[fishtest.stats.stat_util.L(lelo_) for lelo_ in (lelo0,lelo1)]
         nelo0,nelo1=[nelo_divided_by_nt*(score_-0.5)/sigma for score_ in (score0,score1)]
         nelo03,nelo13=[nelo_divided_by_nt*(score_-0.5)/stdev3 for score_ in (score0,score1)]
      else:  ## normalized
         nelo03,nelo13=nelo0,nelo1=elo0_,elo1_
      	 score0,score1=[nelo_/nelo_divided_by_nt*sigma+0.5 for nelo_ in (nelo0,nelo1)]
      	 score03,score13=[nelo_/nelo_divided_by_nt*stdev3+0.5 for nelo_ in (nelo03,nelo13)]
	 lelo0,lelo1=[fishtest.stats.stat_util.elo(score_) for score_ in (score0,score1)]
	 lelo03,lelo13=[fishtest.stats.stat_util.elo(score_) for score_ in (score03,score13)]

      if belo0 is None:
         belo0,belo1=[fishtest.stats.stat_util.elo_to_bayeselo(lelo_, draw_ratio)[0] for lelo_ in (lelo03,lelo13)]	
   
      LLRjumps3=list_to_string([i[0] for i in fishtest.stats.LLRcalc.LLRjumps(pdf3,score0,score1)])
      sp=fishtest.stats.sprt.sprt(alpha=alpha,beta=beta,elo0=lelo0,elo1=lelo1)
      sp.set_state(results3_)
      a3=sp.analytics()
      LLR3_l=a3['a']
      LLR3_u=a3['b']
      if elo_model_=='logistic':
         LLR3=fishtest.stats.LLRcalc.LLR_logistic(lelo03,lelo13,results3_)
      else: # normalized
         LLR3=fishtest.stats.LLRcalc.LLR_normalized(nelo03,nelo13,results3_)
      elo3_l=a3['ci'][0]
      elo3_u=a3['ci'][1]
      elo3=a3['elo']
      LOS3=a3['LOS']
      # auxilliary
      LLR3_exact=N3*fishtest.stats.LLRcalc.LLR(pdf3,score03,score13)
      LLR3_alt  =N3*fishtest.stats.LLRcalc.LLR_alt(pdf3,score03,score13)
      LLR3_alt2 =N3*fishtest.stats.LLRcalc.LLR_alt2(pdf3,score03,score13)
      LLR3_normalized=fishtest.stats.LLRcalc.LLR_normalized(nelo03,nelo13,results3_)
      LLR3_normalized_alt=fishtest.stats.LLRcalc.LLR_normalized_alt(nelo03,nelo13,results3_)
      LLR3_be   =fishtest.stats.stat_util.LLRlegacy(belo0,belo1,results3_)
      if has_pentanomial:	
      	 LLRjumps5=list_to_string([i[0] for i in fishtest.stats.LLRcalc.LLRjumps(pdf5,score0,score1)])
	 sp=fishtest.stats.sprt.sprt(alpha=alpha,beta=beta,elo0=lelo0,elo1=lelo1)
	 sp.set_state(results5_)
	 a5=sp.analytics()
	 LLR5_l=a5['a']
	 LLR5_u=a5['b']
	 if elo_model_=='logistic':
	   LLR5=fishtest.stats.LLRcalc.LLR_logistic(lelo0,lelo1,results5_)
	 else: # normalized
	   LLR5=fishtest.stats.LLRcalc.LLR_normalized(nelo0,nelo1,results5_)
	 o0=0
	 o1=0
	 if o!=None:
	      o0=-o['sq0']/o['m0']/2 if o['m0']!=0 else 0
	      o1=o['sq1']/o['m1']/2 if o['m1']!=0 else 0
	 elo5_l=a5['ci'][0]
	 elo5_u=a5['ci'][1]
	 elo5=a5['elo']
	 LOS5=a5['LOS']
	 # auxilliary
	 LLR5_exact=N5*fishtest.stats.LLRcalc.LLR(pdf5,score0,score1)
	 LLR5_alt  =N5*fishtest.stats.LLRcalc.LLR_alt(pdf5,score0,score1)
	 LLR5_alt2 =N5*fishtest.stats.LLRcalc.LLR_alt2(pdf5,score0,score1)
	 LLR5_normalized=fishtest.stats.LLRcalc.LLR_normalized(nelo0,nelo1,results5_)
	 LLR5_normalized_alt=fishtest.stats.LLRcalc.LLR_normalized_alt(nelo0,nelo1,results5_)

   else:  #assume fixed length test
      elo3,elo95_3,LOS3=fishtest.stats.stat_util.get_elo(results3_)
      elo3_l=elo3-elo95_3
      elo3_u=elo3+elo95_3
      if has_pentanomial:
         elo5,elo95_5,LOS5=fishtest.stats.stat_util.get_elo(results5_)
	 elo5_l=elo5-elo95_5
	 elo5_u=elo5+elo95_5

%>
<!DOCTYPE html>
<html lang="en-us">
  <head>
    <title>Raw statistics for ${run['_id']}</title>
    <link href="https://stackpath.bootstrapcdn.com/twitter-bootstrap/2.3.2/css/bootstrap-combined.min.css"
          integrity="sha384-4FeI0trTH/PCsLWrGCD1mScoFu9Jf2NdknFdFoJhXZFwsvzZ3Bo5sAh7+zL8Xgnd"
          crossorigin="anonymous"
          rel="stylesheet">
    <style>
      td {
        width: 20%;
      }
    </style>
    %if request.cookies.get('theme') == 'dark':
      <link href="/css/theme.dark.css" rel="stylesheet">
    %endif
  </head>
  <body>
% if not has_spsa:
    <div class="row-fluid">
      <div class="span2">
      </div>
      <div class="span8">
      <H3> Raw statistics for ${run['_id']}</H3>
      <em> Unless otherwise specified, all Elo quantities below are logistic. </em>
      <H4> Context </H4>
      	   <table class="table table-condensed">
	   	  <tr><td>Base TC</td><td>${run['args'].get('tc','?')}</td></tr>
	   	  <tr><td>Test TC</td><td>${run['args'].get('new_tc',run['args'].get('tc','?'))}</td></tr>
		  <tr><td>Book</td><td>${run['args'].get('book','?')}</td></tr>
		  <tr><td>Threads</td><td>${run['args'].get('threads','?')}</td></tr>
		  <tr><td>Base options</td><td>${run['args'].get('base_options','?')}</td></tr>
		  <tr><td>New options</td><td>${run['args'].get('new_options','?')}</td></tr>
	</table>
% if has_sprt:
      <H4> SPRT parameters</H4>
      <table class="table table-condensed">
	<tr><td>Alpha</td><td>${alpha}</td></tr>
	<tr><td>Beta</td><td>${beta}</td></tr>
        <tr><td>Elo0 (${elo_model})</td><td>${elo0}</td></tr>
	<tr><td>Elo1 (${elo_model})</td><td>${elo1}</td></tr>
	<tr><td>Batch size (games) </td><td>${batch_size_games}</td></tr>
      </table>
% endif  ## has_sprt
      <H4>Draws</H4>
      <table class="table table-condensed" style="margin-top:1em;">	
	<tr><td>Draw ratio</td><td>${"%.5f"%draw_ratio}</td></tr>
	<tr><td>DrawElo (BayesElo)</td><td>${"%.2f"%drawelo}</td></tr>
      </table>
% if has_sprt:
      <H4> SPRT bounds </H4>
      <table class="table table-condensed" style="margin-top:1em;margin-bottom:0.5em;">	
      <tr>
      <td></td></td><td>Logistic</td><td>Normalized</td><td>BayesElo</td><td>Score</td>
      </tr>
      <tr>
      <td>H0</td><td>${"%.3f"%lelo0}</td><td>${"%.3f"%nelo0}</td><td>${"%.3f"%belo0}</td><td>${"%.5f"%score0}</td>
      </tr>
      <tr>
      <td>H1</td><td>${"%.3f"%lelo1}</td><td>${"%.3f"%nelo1}</td><td>${"%.3f"%belo1}</td><td>${"%.5f"%score1}</td>
      </tr>
      </table>
      <em> Note: normalized Elo is inversely proportional to the square root of the number of games it takes on average to
      detect a given strength difference with a given level of significance. It is given by
      logistic_elo/(2*standard_deviation_per_game). In other words if the draw ratio is zero and Elo differences are small
      then normalized Elo and logistic Elo coincide.
      </em>
% endif  ## has_sprt
% if has_pentanomial:
      <H4> Pentanomial statistics</H4>
      <H5> Basic statistics </H5>
      <table class="table table-condensed">
	<tr><td>Elo</td><td>${"%.4f [%.4f, %.4f]"%(elo5,elo5_l,elo5_u)}</td></tr>
	<tr><td>LOS(1-p)</td><td>${"%.5f"%LOS5}</td></tr>
% if has_sprt:
	<tr><td>LLR</td><td>${"%.4f [%.4f, %.4f]"%(LLR5,LLR5_l,LLR5_u)}</td></tr>
% endif  ## has_sprt
      </table>
% if has_sprt:
      <H5> Generalized Log Likelihood Ratio </H5>
      <table class="table table-condensed" style="margin-top:1em;margin-bottom:0.5em;">
      	<tr><td>Logistic (exact)</td><td>${"%.5f"%LLR5_exact}</td></tr>
      	<tr><td>Logistic (alt)</td><td>${"%.5f"%LLR5_alt}</td></tr>
      	<tr><td>Logistic (alt2)</td><td>${"%.5f"%LLR5_alt2}</td></tr>
	<tr><td>Normalized (exact)</td><td>${"%.5f"%LLR5_normalized}</td></tr>
	<tr><td>Normalized (alt)</td><td>${"%.5f"%LLR5_normalized_alt}</td></tr>
      </table>
      <em> The quantities labeled alt and alt2 are various approximations for the
      exact quantities. Simulations indicate that the exact quantities perform
      better under extreme conditions.
      </em>
% endif ## has_sprt
      <H5> Auxilliary statistics </H5>	
      <table class="table table-condensed">	
	<tr><td>Games</td><td>${int(games5)}</td></tr>
	<tr><td>Results [0-2]</td><td>${results5}</td></tr>
	<tr><td>Distribution</td><td>${pdf5_s}</td></tr>
	<tr><td>(DD,WL) split</td><td>${"(%.5f, %.5f)"%(results5_DD_prob,results5_WL_prob)}</td></tr>
	<tr><td>Expected value</td><td>${"%.5f"%avg5}</td></tr>
	<tr><td>Variance</td><td>${"%.5f"%var5}</td></tr>
	<tr><td>Skewness</td><td>${"%.5f"%skewness5}</td></tr>
	<tr><td>Excess kurtosis</td><td>${"%.5f"%exkurt5}</td></tr>
% if has_sprt:
	<tr><td>Score</td><td>${"%.5f"%(avg5)}</td></tr>
% else:  
	<tr><td>Score</td><td>${"%.5f [%.5f, %.5f]"%(avg5,avg5_l,avg5_u)}</td></tr>
% endif ## has_sprt
	<tr><td>Variance/game</td><td>${"%.5f [%.5f, %.5f]"%(var5_per_game,var5_per_game_l,var5_per_game_u)}</td></tr>
	<tr><td>Stdev/game</td><td>${"%.5f [%.5f, %.5f]"%(stdev5_per_game,stdev5_per_game_l,stdev5_per_game_u)}</td></tr>
% if has_sprt:
	<tr><td>Normalized Elo</td><td>${"%.2f"%(nelo5)}</td></tr>
% else:
	<tr><td>Normalized Elo</td><td>${"%.2f [%.2f, %.2f]"%(nelo5,nelo5_l,nelo5_u)}</td></tr>
% endif  ## has_sprt
% if has_sprt:
	<tr><td>LLR jumps [0-2]</td><td>${LLRjumps5}</td></tr>	
	<tr><td>Expected overshoot [H0,H1]</td><td>${"[%.5f, %.5f]"%(o0,o1)}</td></tr>
% endif  ## has_sprt
      </table>
% endif  ## has_pentanomial
      <H4> Trinomial statistics</H4>
% if has_pentanomial:
     <p>
      <em> The following quantities are computed using the incorrect trinomial model and so they should
      be taken with a grain of salt. The trinomial quantities are listed because they serve as a sanity check
      for the correct pentanomial quantities and moreover it is possible to extract some genuinely
      interesting information from the comparison between the two. </em>
      </p>
% endif  ## has_pentanomial
     <H5> Basic statistics</H5>
      <table class="table table-condensed">
	<tr><td>Elo</td><td>${"%.4f [%.4f, %.4f]"%(elo3,elo3_l,elo3_u)}</td></tr>
	<tr><td>LOS(1-p)</td><td>${"%.5f"%LOS3}</td></tr>
% if has_sprt:
	<tr><td>LLR</td><td>${"%.4f [%.4f, %.4f]"%(LLR3,LLR3_l,LLR3_u)}</td></tr>
% endif  ## has_sprt
      </table>
% if has_sprt:
       <H5> Generalized Log Likelihood Ratio </H5>
       <table class="table table-condensed" style="margin-top:1em;margin-bottom:0.5em;">
       	<tr><td>Logistic (exact)</td><td>${"%.5f"%LLR3_exact}</td></tr>
       	<tr><td>Logistic (alt)</td><td>${"%.5f"%LLR3_alt}</td></tr>
      	<tr><td>Logistic (alt2)</td><td>${"%.5f"%LLR3_alt2}</td></tr>
      	<tr><td>Normalized (exact)</td><td>${"%.5f"%LLR3_normalized}</td></tr>
      	<tr><td>Normalized (alt)</td><td>${"%.5f"%LLR3_normalized_alt}</td></tr>
	<tr><td>BayesElo</td><td>${"%.5f"%LLR3_be}</td></tr>	
	</table>
       <em> Note: BayesElo is the LLR as computed using the BayesElo model. It is not clear how to
       generalize it to the pentanomial case. </em>
% endif  ## has_sprt
     <H5> Auxilliary statistics</H5>
      <table class="table table-condensed">
	<tr><td>Games</td><td>${int(games3)}</td></tr>
	<tr><td>Results [losses, draws, wins]</td><td>${results3}</td></tr>
	<tr><td>Distribution {loss ratio, draw ratio, win ratio}</td><td>${pdf3_s}</td></tr>
	<tr><td>Expected value</td><td>${"%.5f"%avg3}</td></tr>
	<tr><td>Variance</td><td>${"%.5f"%var3}</td></tr>
	<tr><td>Skewness</td><td>${"%.5f"%skewness3}</td></tr>
	<tr><td>Excess kurtosis</td><td>${"%.5f"%exkurt3}</td></tr>
% if has_sprt:
	<tr><td>Score</td><td>${"%.5f"%(avg3)}</td></tr>
% else:
	<tr><td>Score</td><td>${"%.5f [%.5f, %.5f]"%(avg3,avg3_l,avg3_u)}</td></tr>
% endif  ## has_sprt
	<tr><td>Variance/game</td><td>${"%.5f [%.5f, %.5f]"%(var3,var3_l,var3_u)}</td></tr>
	<tr><td>Stdev/game</td><td>${"%.5f [%.5f, %.5f]"%(stdev3,stdev3_l,stdev3_u)}</td></tr>
% if has_sprt:
	<tr><td>Normalized Elo</td><td>${"%.2f"%(nelo3)}</td></tr>
% else:
	<tr><td>Normalized Elo</td><td>${"%.2f [%.2f, %.2f]"%(nelo3,nelo3_l,nelo3_u)}</td></tr>
% endif  ## has_sprt
% if has_sprt:
	<tr><td>LLR jumps [loss, draw, win]</td><td>${LLRjumps3}</td></tr>
% endif  ## has_sprt
      </table>
% if has_pentanomial:
      <H4> Comparison</H4>
      	   <table class="table table-condensed">
		<tr><td>Variance ratio (pentanomial/trinomial)</td><td>${"%.5f"%ratio}</td></tr>
	   	<tr><td>Variance difference (trinomial-pentanomial)</td><td>${"%.5f"%var_diff}</td></tr>
	   	<tr><td>RMS bias</td><td>${"%.5f"%RMS_bias}</td></tr>
	        <tr><td>RMS bias (Elo)</td><td>${"%.3f"%RMS_bias_elo}</td></tr>
	   </table>
% endif  ## has_pentanomial
      </div>
      <div class="span2">
      </div>
% else:  ## not has_spsa / has_spsa
No statistics for spsa tests.
% endif  ## has_spsa
  </body>
</html>
