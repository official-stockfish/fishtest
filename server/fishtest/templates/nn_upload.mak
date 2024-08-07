<%inherit file="base.mak"/>

<script>
  document.title = "Neural Network Upload | Stockfish Testing";
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2 id="upload-heading">Neural Network Upload</h2>
    <div class="alert alert-info" role="alert">
      <p class="mb-0">
        Please read the
        <a
          class="alert-link"
          href="https://github.com/official-stockfish/fishtest/wiki/Creating-my-first-test"
          >Testing Guidelines</a
        >
        before uploading your network.
      </p>
      <p class="mb-0">
        By uploading, you license your network under a
        <a
          class="alert-link"
          href="https://creativecommons.org/share-your-work/public-domain/cc0/"
          >CC0</a
        >
        license.
      </p>
      <p class="mb-0">
        Your uploaded network will be available for public download and listed
        on the <a class="alert-link" href="/nns">NN stats page</a>.
      </p>
    </div>
  </header>

  <form
    id="upload-nn"
    action="${request.url}"
    method="POST"
    enctype="multipart/form-data"
    aria-labelledby="upload-heading"
  >
    <div class="mb-3">
      <label for="network" class="form-label">
        Select your Network file (nn-[SHA256 first 12 digits].nnue)
      </label>
      <input
        class="form-control"
        id="network"
        name="network"
        type="file"
        accept=".nnue"
        aria-describedby="network-help"
      >
      <div id="network-help" class="form-text">
        Only files with a .nnue extension are accepted.
      </div>
    </div>

    <div class="mb-3 form-check">
      <input
        type="checkbox"
        class="form-check-input"
        id="terms-checkbox"
        onclick="doLicense()"
        aria-describedby="terms-help"
      >
      <label class="form-check-label" for="terms-checkbox">
        You are the author of this network or have obtained the network with a
        CC0 license.
      </label>
      <div id="terms-help" class="form-text">
        By checking this box, you confirm that you have the rights to upload this network.
      </div>
    </div>

    <button
      id="upload-button"
      type="submit"
      class="btn btn-primary w-100"
      disabled
      aria-disabled="true"
    >
      Upload
    </button>
  </form>
</div>

<script>
  function doLicense() {
    const uploadButton = document.getElementById("upload-button");
    if (document.getElementById("terms-checkbox").checked) {
      uploadButton.removeAttribute("disabled");
      uploadButton.setAttribute("aria-disabled", "false");
    } else {
      uploadButton.setAttribute("disabled", "");
      uploadButton.setAttribute("aria-disabled", "true");
    }
  }
</script>
