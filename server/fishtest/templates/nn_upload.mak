<%inherit file="base.mak"/>

<style>

  .flex-row {
    display: flex;
    align-items: center;
    margin: 10px 0;
  }

  .field-label {
    font-size: 12px;
    margin: 0;
    text-align: right;
    padding-right: 15px;
    width: 100px;
  }

  .field-label.leftmost {
    width: 75px;
    flex-shrink: 0;
  }

  .rightmost {
    margin-left: auto;
  }

  .third-size {
    width: 107px;
    flex-shrink: 0;
  }

  input.quarter-size {
    margin-right: 10px;
    width: 70px;
    flex-shrink: 0;
  }

  #upload-nn {
    width: 700px;
    margin: 7px auto;
    padding-right: 30px;
  }

  #upload-nn input, #upload-nn select {
    margin: 0;
  }

  .quarter-size {
    width: 80px;
    flex-shrink: 0;
  }

  .choose-test-type .btn {
    width: 75px;
  }

  #upload-nn label:hover {
    cursor: text;
  }

  #upload-nn textarea {
    width: 100%;
    min-height: 40px;
    margin: 0;
  }

  section.test-settings input {
    width: 235px;
  }
</style>

<header style="text-align: center; padding-top: 7px">
  <legend>Neural Network Upload</legend>

  <section class="instructions" style="margin-bottom: 35px">
    <p>
    Please read the
    <a href="https://github.com/glinscott/fishtest/wiki/Creating-my-first-test">Testing Guidelines</a>
    before uploading your network.
    </p>
    <p>
    By uploading you license your network under a
    <a href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.
    </p>
    <p>
    <b>
    <input type="checkbox" id="enable"/ onclick="doLicense()">
    You are the author of this network or have obtained the network with a CC0 license.
    </b>
    </p>
    <p>
    Your uploaded network will be available for public download and listed on the
    <a href="/nns">NN stats page</a>.
    </p>
  </section>
</header>

<form id="upload-nn" action="${request.url}" method="POST" enctype="multipart/form-data">
  <section class="test-settings" style="margin-bottom: 35px">
    <div class="control-group">
      <label class="control-label">Select your Network file (nn-[SHA256 first 12 digits].nnue):</label>
      <div class="controls">
        <input id="network" name="network" type="file" accept=".nnue" value="" />
      </div>
    </div>

    <div class="control-group">
      <div class="controls">
        <button id="upload" type="submit" disabled="true" class="btn btn-primary">Agree to License & Upload</button>
      </div>
    </div>
  </section>
</form>

<script type="text/javascript">
function doLicense() {
  var btn = document.getElementById("upload").disabled = ! document.getElementById("enable").checked;
}
</script>
