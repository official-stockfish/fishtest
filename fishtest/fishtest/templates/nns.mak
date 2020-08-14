<%inherit file="base.mak"/>
<h3>Neural Net download and statistics</h3>

<p>
These networks are available for download under
<a href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.
</p>

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
 %endfor
 </tbody>
</table>
