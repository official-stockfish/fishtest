<%inherit file="base.mak"/>
<h2>User administration</h2>

<form class="form-horizontal" action="${request.url}" method="POST">
  <div class="control-group">
    <label class="control-label">Username:</label>
    <label class="control-label">${user['username']}</label>
  </div>
  <div class="control-group">
    <label class="control-label">eMail:</label>
    <label class="control-label">${user['email']}</label>
  </div>
  <div class="control-group">
    <label class="control-label">Machine Limit:</label>
    <label class="control-label">${limit}</label>
  </div>
  <div class="control-group">
    <label class="control-label">CPU-Hours:</label>
    <label class="control-label">${hours}</label>
  </div>
  <%
  blocked = user['blocked'] if 'blocked' in user else False
  checked = 'checked' if blocked else ''
  %>
  <div class="control-group">
    <label class="control-label">Blocked:</label>
    <label class="control-label"><input name="blocked" type="checkbox" ${checked} value="True">
    </label>
  </div>
  <p>
  <div class="control-group">
    <div class="controls">
      <button type="submit" class="btn btn-primary">Submit</button>
    </div>
  </div>
  </p>
  <input type="hidden" name="user" value="${user['username']}" />
</form>
