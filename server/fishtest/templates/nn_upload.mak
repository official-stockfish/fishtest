<%inherit file="base.mak"/>

<script>
  document.title = 'Neural Network Upload | Stockfish Testing';
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>Neural Network Upload</h2>
    <div class="alert alert-info">
      <p class="mb-0">Please read the <a class="alert-link" href="https://github.com/glinscott/fishtest/wiki/Creating-my-first-test">Testing Guidelines</a> before uploading your network.</p>
      <p class="mb-0">By uploading, you license your network under a <a class="alert-link" href="https://creativecommons.org/share-your-work/public-domain/cc0/">CC0</a> license.</p>
      <p class="mb-0">Your uploaded network will be available for public download and listed on the <a class="alert-link" href="/nns">NN stats page</a>.</p>
    </div>
  </header>

  <form id="upload-nn" action="${request.url}" method="POST" enctype="multipart/form-data">
    <div class="mb-3">
      <label for="network" class="form-label">Select your Network file (nn-[SHA256 first 12 digits].nnue)</label>
      <input class="form-control" id="network" name="network" type="file" accept=".nnue" value="" />
    </div>

    <div class="mb-3 form-check">
      <label for="enable">You are the author of this network or have obtained the network with a CC0 license.</label>
      <input type="checkbox" class="form-check-input" id="enable" onclick="doLicense()">
    </div>

    <button id="upload" type="submit" disabled="true" class="btn btn-primary w-100">Upload</button>
  </form>
</div>

<script>
  function doLicense() {
    var btn = document.getElementById("upload").disabled = ! document.getElementById("enable").checked;
  }
</script>
