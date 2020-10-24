<%inherit file="base.mak"/>

<%block name="head">
  <script src='https://www.google.com/recaptcha/api.js'></script>
</%block>

<div>
  <p></p>
  <p>Signing up to fishtest allows you to contribute with CPU time or with patches to test.</p>
  <p>Your contribution is much appreciated.</p>
  <p>Once a new user account is created, a human needs to manually activate it. This is usually quick, but sometimes takes a few hours.</p>

  <form class="form-horizontal" action="" method="POST">
    <input type="hidden" name="csrf_token"
           value="${request.session.get_csrf_token()}" />
    <legend>Create new user</legend>
    <div class="control-group">
      <label class="control-label">Username:</label>
      <div class="controls">
        <input name="username" pattern="[A-Za-z0-9]{2,}" type="text"
               title="Only letters and digits and at least 2 long" required="required"/>
      </div>
    </div>
    <div class="control-group">
      <label class="control-label">Password:</label>
      <div class="controls">
        <input name="password" type="password" pattern=".{8,}"
               title="Eight or more characters" required="required"/>
      </div>
    </div>
    <div class="control-group">
      <label class="control-label">Repeat password:</label>
      <div class="controls">
        <input name="password2" type="password" required="required"/>
      </div>
    </div>
    <div class="control-group">
      <label class="control-label">E-mail:</label>
      <div class="controls">
        <input name="email" type="email" required="required"/>
      </div>
    </div>
    <div class="control-group">
      <div class="controls">
        <div class="g-recaptcha"
             data-sitekey="6LePs8YUAAAAABMmqHZVyVjxat95Z1c_uHrkugZM"></div>
      </div>
    </div>
    <div class="control-group">
      <div class="controls">
        <button type="submit" class="btn btn-primary">Create User</button>
      </div>
    </div>
  </form>
</div>
