<%inherit file="base.mak"/>
<h3>Neural Net download and statistics</h3>

<p>
These networks are freely available for download and sharing under a
<a href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.<br><br>
Nets colored <span style="background-color:palegreen">green</span> in the table have passed fishtest testing
and achieved the status of <i>default net</i> during the development of Stockfish.<br><br>
The recommended net for a given Stockfish executable can be found as the default value of the EvalFile UCI option.
</p>

<button id="non_default-button" class="btn">
      ${'Hide non default nets' if non_default_shown else 'Show non default nets'}
</button>

<table class="table table-striped table-condensed" style="max-width: 900px;">
 <thead>
  <tr>
   <th>Time</th>
   <th>Network</th>
   <th>Username</th>
   <th>First test</th>
   <th>Last test</th>
   <th style="text-align:right">Downloads</th>
  </tr>
 </thead>
 <tbody>
 %for nn in nns:
  %if request.authenticated_userid or 'first_test' in nn:
  %if non_default_shown or 'is_master' in nn:
  <tr>
   <td>${nn['time'].strftime("%y-%m-%d %H:%M:%S")}</td>
   %if 'is_master' in nn:
   <td style="background-color:palegreen">
   %else:
   <td>
   %endif
   <a href="api/nn/${nn['name']}" style="font-family:monospace">${nn['name']}</a></td>
   <td>${nn['user']}</td>
   <td>
   %if 'first_test' in nn:
   <a href="tests/view/${nn['first_test']['id']}">${str(nn['first_test']['date']).split('.')[0]}</a>
   %endif
   </td>
   <td>
   %if 'last_test' in nn:
   <a href="tests/view/${nn['last_test']['id']}">${str(nn['last_test']['date']).split('.')[0]}</a>
   %endif
   </td>
   <td style="text-align:right">${nn.get('downloads', 0)}</td>
  </tr>
  %endif
  %endif
 %endfor
 </tbody>
</table>
<p>
 %if prev_page:
  <a href="nns?page=${prev_page}">&laquo; Newer nets</a>
 %endif
 %if prev_page and next_page:
  <span>-</span>
 %endif
 %if next_page:
  <a href="nns?page=${next_page}">Older nets &raquo;</a>
 %endif
</p>
