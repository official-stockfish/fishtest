(async () => {
  await DOMContentLoaded();

  const form = document.getElementById("profile_form");
  const githubToken = document.getElementById("github_token");
  const saveTokenButton = document.getElementById("save_github_token");

  if (
    !(form instanceof HTMLFormElement) ||
    !(githubToken instanceof HTMLInputElement) ||
    !(saveTokenButton instanceof HTMLButtonElement) ||
    form.dataset.profileMode !== "1"
  ) {
    return;
  }

  githubToken.value = localStorage.getItem("github_token") || "";
  saveTokenButton.addEventListener("click", () => {
    localStorage.setItem("github_token", githubToken.value);
    if (typeof notifyFishtest === "function") {
      notifyFishtest(
        '<span class="notification-message">Success! GitHub token saved</span>',
      );
    }
    saveTokenButton.textContent = "Saved";
    setTimeout(() => {
      saveTokenButton.textContent = "Save GitHub token";
    }, 1500);
  });
})();
