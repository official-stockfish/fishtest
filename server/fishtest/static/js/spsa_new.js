"use strict";

/*
Quick and dirty way to get the 95% quantile of the
chi2 distribution.
*/

function chi2_95_approximation(df){
    /* Wilson and Hilferty approximation */
    var z95=1.6448536269514722;
    var t=2/(9*df);
    return df*Math.pow(z95*Math.pow(t,0.5)+1-t,3);
}

function chi2_95(df){
    /* Table for df=1,..,99 */
    var chi2_95_=[3.8414588206941236, 5.9914645471079799, 7.8147279032511765, 9.487729036781154, 11.070497693516351, 12.591587243743977,
		  14.067140449340167, 15.507313055865453, 16.918977604620448, 18.307038053275143, 19.675137572682491, 21.026069817483066,
		  22.362032494826941, 23.68479130484058, 24.99579013972863, 26.296227604864235, 27.587111638275324, 28.869299430392626,
		  30.143527205646159, 31.410432844230929, 32.670573340917294, 33.9244384714438, 35.17246162690806, 36.415028501807299,
		  37.652484133482766, 38.885138659830055, 40.113272069413611, 41.337138151427411, 42.556967804292668, 43.772971825742182,
		  44.985343280365129, 46.194259520278457, 47.399883919080921, 48.602367367294178, 49.801849568201824, 50.99846016571064,
		  52.192319730102874, 53.383540622969278, 54.572227758941736, 55.758479278887037, 56.942387146824075, 58.124037680867971,
		  59.303512026899838, 60.480886582336431, 61.656233376279538, 62.829620411408186, 64.001111972218013, 65.170768903569808,
		  66.338648862968768, 67.5048065495412, 68.669293912285838, 69.832160339848173, 70.993452833782186, 72.153216167023089,
		  73.311493029083195, 74.46832415930939, 75.623748469376167, 76.777803156061395, 77.930523805230379, 79.081944487848745,
		  80.232097848762848, 81.381015188899141, 82.528726541471897, 83.675260742721008, 84.820645497656727, 85.964907441231006,
		  87.108072195321995, 88.250164421874018, 89.391207872507835, 90.531225434880668, 91.670239176054821, 92.808270383107839,
		  93.945339601192217, 95.081466669243298, 96.216670753503891, 97.350970379033186, 98.484383459340307, 99.616927324283921,
		  100.74861874635026, 101.87947396543589, 103.00950871222616, 104.13873823027392, 105.26717729686055, 106.39484024272251,
		  107.52174097071949, 108.64789297350764, 109.77330935028799, 110.89800282268439, 112.02198574980785, 113.1452701425555,
		  114.26786767719352, 115.38978970826668, 116.51104728087367, 117.63165114234559, 118.75161175336743, 119.87093929856709,
		  120.98964369660951, 122.10773460981952, 123.22522145336157];
    if(df<=99){
	return chi2_95_[df-1];
    }else{
	return chi2_95_approximation(df);
    }
}

var spsa_setup_default={
    "num_params"   : 1,
    "draw_ratio"   : 0.61,
    "precision"    : 0.5,
    "c_ratio"      : 1/6,
    "lambda_ratio" : 3,
    "params"       : [
	{"name": "dummy",
	 "start": 50,
	 "min" : 0,
	 "max" : 100,
	 "elo" : 2,
	 "c" : null,
	 "r" : null}
    ],
    "num_games"    : null
};


function deepcopy(o){
    return JSON.parse(JSON.stringify(o));
}

function spsa_compute(spsa_setup){
    const C=347.43558552260146;
    var s=deepcopy(spsa_setup);
    var chi2=chi2_95(s.num_params);
    var r=s.precision/(C*chi2*(1-s.draw_ratio)/8);
    var lambda=new Array(s.num_params);
    var i;
    for(i=0;i<s.num_params;i++){
	s.params[i].c=s.c_ratio*(s.params[i].max-s.params[i].min);
	s.params[i].r=r;
	var H_diag=-2*s.params[i].elo/Math.pow((s.params[i].max-s.params[i].min)/2,2);
	lambda[i]=-C/(2*r*Math.pow(s.params[i].c,2)*H_diag);
    }
    var ng;
    s.num_games=-1;
    for(i=0;i<s.num_params;i++){
	ng=Math.round(s.lambda_ratio*lambda[i]);
	if(ng>s.num_games){
	    s.num_games=ng;
	}
    }
    return s;
}

/*
Below is some code to estimate the draw ratio from the time
control. The algorithm is very naive. It uses interpolation for
a few data points valid for the book "noob_3moves.epd".
*/

function tc_to_seconds(tc){
/*
Convert cutechess-cli like tc time[/moves][+inc] to seconds/move.
*/
    var inc=0;
    var moves=68; /* Fishtest average LTC game duration. */
    var time;
    var chunks=tc.split("+");
    if(chunks.length>2){
	return null;
    }
    if(chunks.length==2){
	inc=parseFloat(chunks[1]);
	if(!isFinite(Number(chunks[1])) || !isFinite(inc) || inc<0){
	    return null;
	}
    }
    chunks=chunks[0].split("/");
    if(chunks.length>2){
	return null;
    }
    if(chunks.length==2){
	moves=parseInt(chunks[1]);
	if(!isFinite(Number(chunks[1])) || !isFinite(moves) || moves<=0 ){
	    return null;
	}
    }
    chunks=chunks[0].split(":");
    if(chunks.length>2){
	return null;
    }
    var chunk0=parseFloat(chunks[0]);
	if(!isFinite(Number(chunks[0])) || !isFinite(chunk0) || chunk0<0){
	return null;
    }
    if(chunks.length==1){
	time=chunk0;
    }else{
	var chunk1=parseFloat(chunks[1]);
	if(!isFinite(Number(chunks[1])) || !isFinite(chunk1) || chunk1<0){
	    return null;
	}
	time=60*chunk0+chunk1;
    }
    var tc_seconds=time/moves+inc;
    /* Adhoc for our application: do not allow zero time control */
    if(tc_seconds<=0){
	return null;
    }
    return tc_seconds;
}

function logistic(x){
    return 1/(1+Math.exp(-x));
}

function draw_ratio(tc){
    /*
       Formula approximately valid for the book "noob_3moves.epd".
    */
    const slope=0.372259082112;
    const intercept=0.953433526293;
    var tc_seconds=tc_to_seconds(tc);
    if(tc_seconds==null){
	return null;
    }
    return logistic(slope*Math.log(tc_seconds)+intercept);
}

/*
Now some code to convert Fishtest style spsa data to spsa_setup
objects and back.
*/

function fishtest_to_spsa(fs){
    var s=deepcopy(spsa_setup_default);
    var lines=fs.split("\n");
    var i=0;
    var j=0;
    s.params=[];
    for(i=0;i<lines.length;i++){
	var line=lines[i].trim();
	if(line==""){
	    continue;
	}

	s.params.push({});

	s.params[j].elo=2;

	var chunks=line.split(",");
	if(chunks.length!=6){
	    return null;
	}

	var name=chunks[0];

	var start=parseFloat(chunks[1]);
	if(!isFinite(start)){
	    return null;
	}

	var min=parseFloat(chunks[2]);
	if(!isFinite(min)){
	    return null;
	}

	var max=parseFloat(chunks[3]);
	if(!isFinite(max) || max<=min){
	    return null;
	}

	var c=parseFloat(chunks[4]);
	if(!isFinite(c) || c<=0){
	    return null;
	}

	var r=parseFloat(chunks[5]);
	if(!isFinite(r) || r<=0){
	    return null;
	}

	s.params[j].name=name;
	s.params[j].start=start;
	s.params[j].min=min;
	s.params[j].max=max;
	s.params[j].c=c;
	s.params[j].r=r;

	j++;
    }
    s.num_params=s.params.length;
    if(s.num_params==0){
	return null;
    }
    return s;
}

function spsa_to_fishtest(ss){
    var ret=""
    var i;
    for(i=0;i<ss.params.length;i++){
	var p=ss.params;
	ret+=p[i].name+","+p[i].start+","+p[i].min+","+p[i].max+","+p[i].c.toFixed(2)+","+p[i].r.toFixed(5)+"\n"
    }
    return ret;
}
