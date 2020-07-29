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
   <th>Downloads</th>
  </tr>
 </thead>
 <tbody>
 %for nn in nns:
  <tr>
   <td>${nn['time'].strftime("%y-%m-%d %H:%M:%S")}</td>
   <td><a href="api/nn/${nn['name']}">${nn['name']}</a></td>
   <td>${nn['user']}</td>
   <td>${nn.get('downloads', 0)}</td>
  </tr>
 %endfor
 </tbody>
</table>
