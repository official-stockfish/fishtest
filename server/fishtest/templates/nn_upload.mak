<%inherit file="base.mak"/>

<script>
  document.title = "Neural Network Upload | Stockfish Testing";
</script>

<div class="col-limited-size">
  <header class="text-md-center py-2">
    <h2>Neural Network Upload</h2>
    <div class="alert alert-info">
      <p class="mb-0">
        Please read the
        <a
          class="alert-link"
          href="https://github.com/official-monty/montytest/wiki/Creating-my-first-test"
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
  >
    <div class="mb-3">
      <label for="network" class="form-label">
        Select your Network file (nn-[SHA256 first 12 digits].network)
      </label>
      <input
        class="form-control"
        id="network"
        name="network"
        type="file"
        accept=".network"
      >
    </div>

    <div class="mb-3 form-check">
      <label class="form-check-label" for="terms-checkbox">
        You are the author of this network or have obtained the network with a
        CC0 license.
      </label>
      <input
        type="checkbox"
        class="form-check-input"
        id="terms-checkbox"
        onclick="doLicense()"
      >
    </div>

    <button
      id="upload-button"
      type="submit"
      class="btn btn-primary w-100"
      disabled
    >
      Upload
    </button>
  </form>
</div>

<script>
  function doLicense() {
    if (document.getElementById("terms-checkbox").checked) {
      document.getElementById("upload-button").removeAttribute("disabled");
    } else {
      document.getElementById("upload-button").setAttribute("disabled", "");
    }
  }
</script>
