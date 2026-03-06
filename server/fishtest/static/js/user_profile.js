(async () => {
  await DOMContentLoaded();

  const form = document.getElementById("profile_form");
  const githubToken = document.getElementById("github_token");

  if (
    !(form instanceof HTMLFormElement) ||
    !(githubToken instanceof HTMLInputElement) ||
    form.dataset.profileMode !== "1"
  ) {
    return;
  }

  githubToken.value = localStorage.getItem("github_token") || "";
  form.addEventListener("submit", () => {
    localStorage.setItem("github_token", githubToken.value);
  });
})();
