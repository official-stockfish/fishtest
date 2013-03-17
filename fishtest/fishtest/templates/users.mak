<%inherit file="base.mak"/>

<h3>Users</h3>
<ul>
 %for user in users:
 <li>${user}</li>
 %endfor
</ul>
