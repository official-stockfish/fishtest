<%inherit file="base.mak"/>

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
    You are the author of this network or have obtained the network with a CC0 license.
    </p>
    <p>
    Your uploaded network will be available for public download and listed on the
    <a href="/nns">NN stats page</a>.
    </p>
  </section>
</header>

<div>
  <form id="upload-nn" action="${request.url}" method="POST" enctype="multipart/form-data">
    <div class="control-group">
    <label class="control-label">Select your Network file (nn-[SHA256 first 12 digits].nnue):</label>
      <div class="controls">
        <input id="network" name="network" type="file" value="" />
      </div>
    </div>

    <div class="control-group">
      <div class="controls">
        <button type="submit" class="btn btn-primary">Agree to License & Upload</button>
      </div>
    </div>
  </form>
</div>
