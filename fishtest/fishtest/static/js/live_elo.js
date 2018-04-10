"use strict";

google.charts.load('current', {'packages':['gauge']});
var LOS_chart=null;
var LLR_chart=null;
var ELO_chart=null;

window.onpopstate=function(e){
    displayURL(e.state);
};
                
var Module={};
// Emscripten callback. 
Module.onRuntimeInitialized=function() {
    history.replaceState(""+location,"","");
    google.charts.setOnLoadCallback(function(){
        LOS_chart = new google.visualization.Gauge(document.getElementById('LOS_chart_div'));
        LLR_chart = new google.visualization.Gauge(document.getElementById('LLR_chart_div'));
        ELO_chart = new google.visualization.Gauge(document.getElementById('ELO_chart_div'));
        clear_gauges();
        displayURL(""+window.location)
    });
}

function compute(export_arguments){
    var m=export_arguments;
    var ret=Module.ccall('export_json',
                         'string',
                         ['number','number','number','number','number','number','number','number','number'],
                         [m.alpha,m.beta,m.elo0,m.elo1,m.level,0,m.W,m.D,m.L]);
    return JSON.parse(ret);
}

var Tab_list={};

Tab_list.active=function(){
    var ret="";
    var activeElement=document.querySelector("#_tab_list .active");
    if(activeElement){
        ret=activeElement.parentNode.id.slice(1);
    }
    return ret;
}

Tab_list.set_active=function(id){
    var activeElement=document.querySelector("#_tab_list .active");
    var newActiveElement=document.querySelector('#_'+id+' span');
    if(activeElement!==newActiveElement){
        if(activeElement){
            activeElement.classList.remove("active");
        }
        if(newActiveElement){
            newActiveElement.classList.add("active");
        }
    }
}

Tab_list.delete_active=function() {
    var id=Tab_list.active();
    if(id){
        var currentElement=document.getElementById("_"+id);
        if(currentElement){
            currentElement.parentNode.removeChild(currentElement);
            document.getElementById("live").value="";
            follow_live(false);
            sessionStorage.removeItem("live");
            Tab_list.setURL();
        }
    }
}

Tab_list.add=function(id,name,push) {
    var currentElement=document.getElementById("_"+id);
    if(!currentElement){
        var tab_listElement=document.getElementById("_tab_list");
        var new_tabElement=document.getElementById("_new");
        var insertElement=new_tabElement.cloneNode(true);
        tab_listElement.insertBefore(insertElement,new_tabElement);
        insertElement.id="_"+id;
        insertElement.style.visibility="visible";
        var spanElement=document.querySelector('#_'+id+' span');
        spanElement.innerHTML=name.slice(0,10)+"...";
        spanElement.classList.remove("active");
        if(push){
            Tab_list.setURL();
        }
    }
    Tab_list.set_active(id);
}

Tab_list.show=function(id){
    Tab_list.set_active(id);
    document.getElementById("live").value=sanitizeURL(id);
    follow_live(true);
}

Tab_list.setURL=function(){
    var children=document.querySelectorAll("#_tab_list>*");
    var url=window.location.pathname+"?";
    for(var i=0; i<children.length; i++){
        var childElement=children[i];
        var id=childElement.id.slice(1);
        var spanElement=document.querySelector('#_'+id+' span');
        name=spanElement.innerHTML;
        if(id!="new"){
            url+=id+"="+encodeURI(name)+"&";
        }
    }
    history.pushState(url,"",url);
}

Tab_list.reset=function(){
    var children=document.querySelectorAll("#_tab_list>*");
    for(var i=0; i<children.length; i++){
        var childElement=children[i];
        if(childElement.id!="_new"){
            childElement.parentNode.removeChild(childElement);
        }
    }
}

function displayURL(url){
    var args=url.split("?");
    if(args.length>=2){
        args=args[1];
    }else{
        args="";
    }
    var liveElement=document.getElementById("live");
    Tab_list.reset();
    liveElement.value="";
    if(args!=""){
        args=args.split("&");
        for(var i=0;i<args.length;i++){
            var arg=args[i];
            if(arg){
                var split=arg.split('=');
                if(split.length>=1){
                    var id=decodeURL(split[0]);
                    liveElement.value=sanitizeURL(id);
                    if(split.length==2){
                        Tab_list.add(split[0],decodeURI(split[1]),false);
                    }else if(split.length==1){
                        Tab_list.add(split[0],split[0],false);
                    }
                }
            }
        }
    }
    follow_live(true);
}

function decodeURL(url){
    var test_=url.split("/").pop().trim();
    var re=/^[0-9a-f]*$/;
    if(test_.match(re) && test_.length==24){
        return test_;
    }
    return null;
}

function sanitizeURL(url){
    var test=decodeURL(url);
    if(test!=null){
        return "/tests/view/"+test;
    }else{
        return "";
    }
}

var ItemEnum={
    no_error              :  0,
    network_error         :  1,
    internal_server_error :  2,
    not_a_valid_url       :  3,
    pending               :  4,
    no_id                 :  5,
    no_diff               :  6,
    not_SPRT              :  7,
    no_test_data          :  8,
    no_commit             :  9,
    no_sprt_state         : 10,
    no_tc                 : 11,
    no_username           : 12,
    no_info               : 13,
    general_error         : 99
}

function extract_items(text){
    var start,end,text2,ret,re;
    var items={
        id                    : "",
        diff                  : "",
        commit                : "",
        info                  : "",
        export_arguments      : {level: 0.95},
        return_code           : ItemEnum.no_error,
        msg                   : "No error."
    }

    start=text.indexOf("<html><body>Network error.</body></html>");
    if(start!=-1){
        items.return_code=ItemEnum.not_a_valid_url;
        items.msg="Unable to load URL.";
        return items;
    }

    start=text.indexOf('">Pending...');
    if(start!=-1){
        items.return_code=ItemEnum.pending;
        items.msg="This test is still pending.";
        return items;
    }

    var diff=/<h3>[^]*?<a href="([^"]*)/g;
    ret=diff.exec(text);
    if(!ret){
        items.return_code=ItemEnum.no_diff;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.diff=ret[1];
    
    var sprt=/LLR: [0-9\-\.]* \([0-9\-\.,]*\) \[[0-9\-\.,]*\]\s*.*\s*Total: [0-9]* W: ([0-9]*) L: ([0-9]*) D: ([0-9]*)/g;
    sprt.lastIndex=diff.lastIndex;
    ret=sprt.exec(text);
    if(!ret){
        items.return_code=ItemEnum.not_SPRT;
        items.msg="This is not a SPRT test.";
        return items;
    }
    items.export_arguments.W=Number(ret[1]);
    items.export_arguments.L=Number(ret[2]);
    items.export_arguments.D=Number(ret[3]);

    var id=/<tr><td>id<\/td><td>([0-9a-f]{24})<\/td><\/tr>/g;
    ret=id.exec(text);
    id.lastIndex=sprt.lastIndex;
    if(!ret){
        items.return_code=ItemEnum.no_id;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.id=ret[1];
    
    var new_tag=/<tr><td>new_tag<\/td><td>[^>]*>([^]*?)<\/a><\/td><\/tr>/g;
    new_tag.lastIndex=id.lastIndex;
    ret=new_tag.exec(text);
    if(!ret){
        items.return_code=ItemEnum.no_commit;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.commit=ret[1];
    
    var sprt_state=/<tr><td>sprt<\/td><td>elo0: ([0-9\.\-]*) alpha: ([0-9\.]*) elo1: ([0-9\.\-]*) beta: ([0-9\.]*) state: ([a-z\-]*)<\/td><\/tr>/g;
    sprt_state.lastIndex=new_tag.lastIndex;
    ret=sprt_state.exec(text);
    if(!ret){
        items.return_code=ItemEnum.no_sprt_state;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.export_arguments.elo0=Number(ret[1]);
    items.export_arguments.alpha=Number(ret[2]);
    items.export_arguments.elo1=Number(ret[3]);
    items.export_arguments.beta=Number(ret[4]);
    items.state=ret[5];

    var tc=/<tr><td>tc<\/td><td>([^<]*)<\/td><\/tr>/g;
    tc.lastIndex=sprt_state.lastIndex;
    ret=tc.exec(text);
    if(!ret){
        items.return_code=ItemEnum.no_tc;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.tc=ret[1];
    
    var username=/<tr><td>username<\/td><td>(.*)<\/td><\/tr>/g;
    username.lastIndex=tc.lastIndex;
    ret=username.exec(text);
    if(!ret){
        items.return_code=ItemEnum.no_username;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.username=ret[1];
    
    var info=/<tr><td>info<\/td><td>([^]*?)<\/td><\/tr>/g;
    info.lastIndex=username.lastIndex;
    ret=info.exec(text);
    if(!ret){
        items.return_code=ItemEnum.no_info;
        items.msg="Parse error: "+items.return_code;
        return items;
    }
    items.info=ret[1];

    return items;
}

function set_gauges(LLR,a,b,LOS,elo,ci_lower,ci_upper){
    if(!set_gauges.last_elo){
        set_gauges.last_elo=0;
    }
    var LOS_chart_data = google.visualization.arrayToDataTable([
        ['Label', 'Value'],
        ['LOS', Math.round(1000*LOS)/10]
    ]);
    var LOS_chart_options = {
        width: 500, height: 150,
        greenFrom: 95, greenTo: 100,
        yellowFrom:5, yellowTo: 95,
        redFrom:0, redTo: 5,
        minorTicks: 5
    };
    LOS_chart.draw(LOS_chart_data, LOS_chart_options);

    var LLR_chart_data = google.visualization.arrayToDataTable([
        ['Label', 'Value'],
        ['LLR', Math.round(100*LLR)/100]
    ]);
    a=Math.round(100*a)/100;
    b=Math.round(100*b)/100;
    var LLR_chart_options = {
        width: 500, height: 150,
        yellowFrom: a, yellowTo: b,
        max:b, min: a,
        minorTicks: 5
    };
    LLR_chart.draw(LLR_chart_data, LLR_chart_options);

    var ELO_chart_data = google.visualization.arrayToDataTable([
        ['Label', 'Value'],
        ['Elo', set_gauges.last_elo]
    ]);
    var ELO_chart_options = {
        width: 500, height: 150,
        max:6, min: -6,
        minorTicks: 5
    };
    if(ci_lower<0 && ci_upper>0){
        ELO_chart_options.redFrom=ci_lower;
        ELO_chart_options.redTo=0;
        ELO_chart_options.greenFrom=0;
        ELO_chart_options.greenTo=ci_upper;
    }else if(ci_lower>=0){
        ELO_chart_options.greenFrom=ci_lower;
        ELO_chart_options.greenTo=ci_upper;
    }else if(ci_upper<=0){
        ELO_chart_options.redFrom=ci_lower;
        ELO_chart_options.redTo=ci_upper;
    }
    ELO_chart.draw(ELO_chart_data, ELO_chart_options); 
    elo=Math.round(100*elo)/100;
    ELO_chart_data.setValue(0, 1, elo);
    ELO_chart.draw(ELO_chart_data, ELO_chart_options); // 2nd draw to get animation
    set_gauges.last_elo=elo;
}

function clear_gauges(){
    set_gauges(0,-2.94,2.94,0.50,0,0,0);
}

function display_data(items){
    Tab_list.add(items.id,items.commit,true);
    var link=sanitizeURL(items.id);

    var j=compute(items.export_arguments);
    document.getElementById("error").style.display="none";
    document.getElementById("data").style.visibility="visible";
    document.getElementById("commit").innerHTML="<a href="+items.diff+">"+items.commit+"</a>";
    document.getElementById("username").innerHTML=items.username;
    document.getElementById("tc").innerHTML=items.tc;
    document.getElementById("info").innerHTML=items.info;
    document.getElementById("sprt").innerHTML="elo0:&nbsp;"+j.elo_raw0.toFixed(2)+"&nbsp;&nbsp;alpha:&nbsp;"+j.alpha.toFixed(2)+"&nbsp;&nbsp;elo1:&nbsp;"+j.elo_raw1.toFixed(2)+"&nbsp;&nbsp;beta:&nbsp;"+j.beta.toFixed(2);
    document.getElementById("elo").innerHTML=j.elo.toFixed(2)+" ["+j.ci_lower.toFixed(2)+","+j.ci_upper.toFixed(2)+"] ("+100*(1-j.p).toFixed(2)+"%"+")";
    document.getElementById("LLR").innerHTML=j.LLR.toFixed(2)+" ["+j.a.toFixed(2)+","+j.b.toFixed(2)+"]"+(items.state!="-"?" ("+items.state+")":"");
    document.getElementById("LOS").innerHTML=""+(100*j.LOS).toFixed(1)+"%";
    document.getElementById("games").innerHTML=j.games+" [w:"+(100*j.W/j.games).toFixed(1)+"%, l:"+(100*j.L/j.games).toFixed(1)+"%, d:"+(100*j.D/j.games).toFixed(1)+"%]";

    document.getElementById("link").innerHTML="<a href="+link+">"+link+"</a>";
    set_gauges(j.LLR,j.a,j.b,j.LOS,j.elo,j.ci_lower,j.ci_upper);
}

function alert_(message){
    document.getElementById("data").style.visibility="hidden";
    clear_gauges();
    var errorElement=document.getElementById("error");
    if(message==""){
        errorElement.style.display="none";
    }else{
        errorElement.style.display="block";
        errorElement.innerHTML='<i class="material-icons" style="vertical-align:bottom;">error</i> '+message;
    }
}

// Main worker.
function follow_live(retry){
    if(follow_live.timer_once===undefined){
        follow_live.timer_once=null;
    }
    if(follow_live.timer_once!=null){
        clearTimeout(follow_live.timer_once);
        follow_live.timer_once=null;
    }
    var testURL=document.getElementById("live").value;
    var test=decodeURL(testURL);
    if(testURL!="" && !test){
        alert_("This is not the URL of a test.");
        return;
    }
    if(testURL==""){
        alert_("");
        return;
    }
    var xhttp = new XMLHttpRequest();
    var timestamp=(new Date()).getTime();
    xhttp.open("GET", "/tests/view/"+test, true);
    xhttp.onreadystatechange = function() {
        if (this.readyState == 4) {
            if(this.status == 200){
                let items=extract_items(this.responseText);
                if(items.return_code==ItemEnum.no_error){
                    display_data(items);
                    if(items.state=="-"){
                        follow_live.timer_once=setTimeout(follow_live,20000,true);
                    }
                }else{
                    alert_(items.msg);
                }
            }else{
                if(retry){
                    follow_live.timer_once=setTimeout(follow_live,20000,true);
                }else{
                   alert_("Network or server error.");
                }
            }
        }
    }
    xhttp.send();
}



