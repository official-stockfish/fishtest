<%inherit file="base.mak"/>
<h3>Neural Net download and statistics</h3>

<p>
These networks are available for download under
<a href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.
</p>

<table class="table table-striped table-condensed" style="max-width: 700px;">
 <thead>
  <tr>
   <th>Time</th>
   <th>Network</th>
   <th>Username</th>
   <th style="text-align:right">Downloads</th>
  </tr>
 </thead>
 <tbody>
 %for nn in nns:
  <tr>
   <td>${nn['time'].strftime("%y-%m-%d %H:%M:%S")}</td>
   <td><a href="api/nn/${nn['name']}" style="font-family:monospace">${nn['name']}</a></td>
   <td>${nn['user']}</td>
   <td style="text-align:right">${nn.get('downloads', 0)}</td>
  </tr>
 %endfor
 </tbody>
</table>
