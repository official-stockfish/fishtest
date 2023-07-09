(() => {
  "use strict";

  const togglePasswordVisibility = document.querySelectorAll(
    ".toggle-password-visibility",
  );
  togglePasswordVisibility.forEach((toggle) => {
    toggle.addEventListener("click", (event) => {
      const input = event.target.parentNode.querySelector("input");
      const icon = event.target.querySelector("i");
      input.type = input.type === "password" ? "text" : "password";
      icon.classList.toggle("fa-eye");
      icon.classList.toggle("fa-eye-slash");
    });
  });
})();
