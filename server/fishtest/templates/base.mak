<!doctype html>
<html lang="en">
  <head>
    <title>Monty Testing Framework</title>
    <meta name="csrf-token" content="${request.session.get_csrf_token()}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <script>
      const darkThemeHash = "${cache_busters['css/theme.dark.css']}";
    </script>

    <link
      rel="stylesheet"
      href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css"
      integrity="sha512-z3gLpd7yknf1YoNbCzqRKc4qyor8gaKU1qmn+CShxbuBusANI9QpRohGBreCFkKxLhei6S9CQXFEbbKuqLg0DA=="
      crossorigin="anonymous"
      referrerpolicy="no-referrer"
    >

    <link
      rel="stylesheet"
      href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.1/css/bootstrap.min.css"
      integrity="sha512-Z/def5z5u2aR89OuzYcxmDJ0Bnd5V1cKqBEbvLOiUNWdg9PQeXVvXLI90SE4QOHGlfLqUnDNVAYyZi8UwUTmWQ=="
      crossorigin="anonymous"
      crossorigin="anonymous"
      referrerpolicy="no-referrer"
    >

    <link
      rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/skeleton-screen-css@1.1.0/dist/index.min.css"
      integrity="sha384-bVhC78CCZuU0Ls4O2v9Jvh01lwXOdpJm+f1HFJZ81vNIB+S88EM7jx/vyLOlQUGC"
      crossorigin="anonymous"
    >

    <link
      rel="stylesheet"
      href="/css/application.css?v=${cache_busters['css/application.css']}"
      integrity="sha384-${cache_busters['css/application.css']}"
      crossorigin="anonymous"
    >

    % if request.cookies.get('theme') == 'dark':
    <link
      rel="stylesheet"
      href="/css/theme.dark.css?v=${cache_busters['css/theme.dark.css']}"
      integrity="sha384-${cache_busters['css/theme.dark.css']}"
      crossorigin="anonymous"
    >
    % endif

    <script
      src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.1/js/bootstrap.bundle.min.js"
      integrity="sha512-ToL6UYWePxjhDQKNioSi4AyJ5KkRxY+F1+Fi7Jgh0Hp5Kk2/s8FD7zusJDdonfe5B00Qw+B8taXxF6CFLnqNCw=="
      crossorigin="anonymous"
      crossorigin="anonymous"
      referrerpolicy="no-referrer"
    ></script>

    <script
      src="/js/application.js?v=${cache_busters['js/application.js']}"
      integrity="sha384-${cache_busters['js/application.js']}"
      crossorigin="anonymous"
    ></script>

    <script
      src="/js/notifications.js?v=${cache_busters['js/notifications.js']}"
      integrity="sha384-${cache_busters['js/notifications.js']}"
      crossorigin="anonymous"
    ></script>

    <%block name="head"/>
  </head>

  <body>
    <header class="navbar navbar-expand-lg sticky-top shadow-sm">
      <nav
        class="container-fluid flex-wrap flex-lg-nowrap"
        aria-label="Main navigation"
      >
        <button
          class="navbar-toggler p-2"
          type="button"
          data-bs-toggle="offcanvas"
          data-bs-target="#leftsidebar"
          aria-controls="leftsidebar"
          aria-expanded="false"
          aria-label="Toggle left sidebar navigation"
        >
          <i class="fa-solid fa-bars"></i>
        </button>

        <a
          class="navbar-brand p-0 me-0 me-lg-2 d-flex align-items-center"
          href="/"
          aria-label="Bootstrap"
        >
          <div class="brand-logo d-inline me-lg-2"></div>
          <p class="d-none d-lg-inline h-5 mb-0">Monty Testing Framework</p>
        </a>

        <button
          class="navbar-toggler d-flex d-lg-none order-3 p-2"
          type="button"
          data-bs-toggle="offcanvas"
          data-bs-target="#rightsidebar"
          aria-controls="rightsidebar"
          aria-expanded="false"
          aria-label="Toggle user navigation"
        >
          <i class="fa-solid fa-ellipsis"></i>
        </button>

        <div
          class="offcanvas-lg offcanvas-end flex-grow-1"
          id="rightsidebar"
          aria-labelledby="rightsidebarOffcanvasLabel"
          data-bs-scroll="true"
        >
          <div class="offcanvas-header px-4 pb-0">
            <h5 class="offcanvas-title" id="rightsidebarOffcanvasLabel">
              User
            </h5>
            <button
              type="button"
              class="btn-close"
              data-bs-dismiss="offcanvas"
              aria-label="Close"
              data-bs-target="#rightsidebar"
            ></button>
          </div>

          <div class="offcanvas-body p-4 pt-0 p-lg-0">
            <hr class="d-lg-none">

            <ul class="navbar-nav flex-row flex-wrap ms-md-auto">
              % if request.authenticated_userid:
                <li class="nav-item col-6 col-lg-auto order-lg-2">
                  <a
                    class="nav-link py-2 px-0 px-lg-2"
                    href="/tests/user/${request.authenticated_userid}"
                    title="My Tests"
                  >
                    <i class="fa-solid fa-flask d-inline me-2 mx-lg-1"></i>
                    <span class="d-inline d-lg-none">My Tests</span>
                  </a>
                </li>
                <li class="nav-item col-6 col-lg-auto order-lg-1">
                  <a
                    class="nav-link py-2 px-0 px-lg-2"
                    href="/tests/run"
                    title="New Test"
                  >
                    <i class="fa-solid fa-plus d-inline me-2 mx-lg-1"></i>
                    <span class="d-inline d-lg-none">New Test</span>
                  </a>
                </li>
                <li class="nav-item col-6 col-lg-auto order-lg-0">
                  <a
                    class="nav-link py-2 px-0 px-lg-2"
                    href="/upload"
                    title="Upload Neural Network"
                  >
                    <i
                      class="fa-solid fa-cloud-arrow-up d-inline me-2 mx-lg-1"
                    ></i>
                    <span class="d-inline d-lg-none">NN Upload</span>
                  </a>
                </li>
                <li class="nav-item py-1 col-12 col-lg-auto order-lg-2">
                  <div class="vr d-none d-lg-flex h-100 mx-lg-2"></div>
                  <hr class="d-lg-none">
                </li>
                <li class="nav-item col-6 col-lg-auto order-lg-2">
                  <a class="nav-link py-2 px-0 px-lg-2" href="/user"
                    ><i class="fa-solid fa-user d-inline d-lg-none me-2"></i
                    >Profile
                  </a>
                </li>
                <li class="nav-item col-6 col-lg-auto order-lg-2">
                  <a class="nav-link py-2 px-0 px-lg-2" href="/logout" id="logout"
                    ><i
                      class="fa-solid fa-arrow-right-from-bracket d-inline d-lg-none me-2"
                    ></i
                    >Logout
                  </a>
                </li>
              % else:
                <li class="nav-item col-6 col-lg-auto order-lg-2">
                  <a class="nav-link py-2 px-0 px-lg-2" href="/login"
                    ><i
                      class="fa-solid fa-arrow-right-to-bracket d-inline d-lg-none me-2"
                    ></i
                    >Login</a
                  >
                </li>
                <li class="nav-item col-6 col-lg-auto order-lg-2">
                  <a class="nav-link py-2 px-0 px-lg-2" href="/signup"
                    ><i class="fa-solid fa-user-plus d-inline d-lg-none me-2"></i
                    >Register</a
                  >
                </li>
              % endif
              <li class="nav-item py-1 col-12 col-lg-auto order-lg-2">
                <div class="vr d-none d-lg-flex h-100 mx-lg-2"></div>
                <hr class="d-lg-none">
              </li>
              <li
                class="nav-item col-6 col-lg-auto order-lg-2"
                id="change-color-theme"
              >
                <div
                  id="sun"
                  style="display: ${'none;' if request.cookies.get('theme') != 'dark' else 'inline-block;'}"
                  class="nav-link py-2 px-0 px-lg-2"
                  title="Light Theme"
                >
                  <i class="fa fa-sun"></i
                  ><span class="d-inline d-lg-none ms-2">Light Theme</span>
                </div>
                <div
                  id="moon"
                  style="display: ${'none;' if request.cookies.get('theme') == 'dark' else 'inline-block;'}"
                  class="nav-link py-2 px-0 px-lg-2"
                  title="Dark Theme"
                >
                  <i class="fa fa-moon"></i>
                  <span class="d-inline d-lg-none ms-2">Dark Theme</span>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </nav>
    </header>

    <div class="container-fluid layout px-0">
      <aside class="mainnavbar ps-lg-1">
        <div
          class="offcanvas-lg offcanvas-start"
          id="leftsidebar"
          aria-labelledby="leftsidebarOffcanvasLabel"
        >
          <div class="offcanvas-header border-bottom">
            <h5 class="offcanvas-title" id="leftsidebarOffcanvasLabel">
              Fishtest
            </h5>
            <button
              type="button"
              class="btn-close"
              data-bs-dismiss="offcanvas"
              aria-label="Close"
              data-bs-target="#leftsidebar"
            ></button>
          </div>
          <div class="offcanvas-body pt-lg-2">
            <nav class="links w-100">
              <ul class="links-nav list-unstyled mb-0 pb-3 pb-md-2 pe-lg-1">
                <li class="links-group">
                  <strong
                    class="links-heading d-flex w-100 align-items-center fw-semibold"
                    >Tests</strong
                  >
                  <ul class="list-unstyled fw-normal small">
                    <li>
                      <a href="/tests" class="links-link rounded">Overview</a>
                    </li>
                    <li>
                      <a
                        href="/tests/finished?ltc_only=1"
                        class="links-link rounded"
                        >LTC</a
                      >
                    </li>
                    <li>
                      <a
                        href="/tests/finished?success_only=1"
                        class="links-link rounded"
                        >Greens</a
                      >
                    </li>
                    <li>
                      <a
                        href="/tests/finished?yellow_only=1"
                        class="links-link rounded"
                        >Yellows</a
                      >
                    </li>
                  </ul>
                </li>

                <li><hr class="my-1"></li>

                <li class="links-group">
                  <strong
                    class="links-heading d-flex w-100 align-items-center fw-semibold"
                    >Fishtest</strong
                  >
                  <ul class="list-unstyled fw-normal small">
                    <li>
                      <a href="/contributors" class="links-link rounded"
                        >Contributors</a
                      >
                    </li>
                    <li>
                      <a href="/contributors/monthly" class="links-link rounded"
                        >Top Month</a
                      >
                    </li>
                    <li>
                      <a href="/actions" class="links-link rounded">Events</a>
                    </li>
                    <li>
                    % if len(request.userdb.get_pending()) > 0:
                      <a
                        href="/user_management"
                        class="links-link rounded text-danger"
                        >Users (${len(request.userdb.get_pending())})</a
                      >
                    % else:
                      <a href="/user_management" class="links-link rounded"
                        >Users</a
                      >
                    % endif
                    </li>
                    <li>
                      <a href="/workers/show" class="links-link rounded"
                        >Blocked Workers</a
                      >
                    </li>
                  </ul>
                </li>

                <li><hr class="my-1"></li>

                <li class="links-group">
                  <strong
                    class="links-heading d-flex w-100 align-items-center fw-semibold"
                    >Monty</strong
                  >
                  <ul class="list-unstyled fw-normal small">
                    <li>
                      <a
                        href="https://montychess.org/download/"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded release"
                        >Official Releases</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/Monty/releases?q=prerelease%3Atrue"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded release"
                        >Prereleases</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://montychess.org/get-involved/"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded get-involved"
                        >Contribute</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/Monty/wiki/Regression-Tests"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded regression"
                        >Progress</a
                      >
                    </li>
                    <li>
                      <a href="/nns" class="links-link rounded">NN Repo</a>
                    </li>
                  </ul>
                </li>

                <li><hr class="my-1"></li>

                <li class="links-group">
                  <strong
                    class="links-heading d-flex w-100 align-items-center fw-semibold"
                    >Resources</strong
                  >
                  <ul class="list-unstyled fw-normal small">
                    <li>
                      <a
                        href="https://discord.gg/awnh2qZfTT"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded discord"
                        >Discord</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/fishtest/wiki"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded wiki"
                        >Fishtest Wiki</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/Monty/wiki"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded wiki"
                        >Monty Wiki</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/nnue-pytorch/wiki"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded wiki"
                        >NN Trainer Wiki</a
                      >
                    </li>
                    <li>
                      <a href="/sprt_calc" class="links-link rounded"
                        >SPRT Calc</a
                      >
                    </li>
                  </ul>
                </li>

                <li><hr class="my-1"></li>

                <li class="links-group">
                  <strong
                    class="links-heading d-flex w-100 align-items-center fw-semibold"
                    >Development</strong
                  >
                  <ul class="list-unstyled fw-normal small">
                    <li>
                      <a
                        href="https://github.com/official-monty/Monty"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded Monty-repo"
                        >Monty</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/fishtest"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded"
                        >Fishtest</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/nnue-pytorch"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded"
                        >NN Trainer</a
                      >
                    </li>
                    <li>
                      <a
                        href="https://github.com/official-monty/books"
                        target="_blank"
                        rel="noopener"
                        class="links-link rounded"
                        >Books</a
                      >
                    </li>
                  </ul>
                </li>
              </ul>
            </nav>
          </div>
        </div>
      </aside>

      <main class="main order-1">
        <div class="container-fluid">
          <div class="row">
            <div class="flash-message mt-3">
              <div
                id="fallback_div"
                class="alert alert-success alert-dismissible alert-success-non-transparent fixed-top"
                style="display: none"
              >
                <span id="fallback">Notification!</span>
                <button
                  type="button"
                  id="fallback_button"
                  class="btn-close"
                  aria-label="Close"
                ></button>
                <script>
                  const fallback_button =
                    document.getElementById("fallback_button");
                  fallback_button.addEventListener("click", () => {
                    dismissNotification("fallback_div");
                  });
                </script>
              </div>
              <div
                id="error_div"
                class="alert alert-danger alert-dismissible alert-danger-non-transparent fixed-top"
                style="display: none"
              >
                <span id="error"></span>
                <button
                  type="button"
                  id="error_button"
                  class="btn-close"
                  aria-label="Close"
                ></button>
                <script>
                  const error_button =
                    document.getElementById("error_button");
                  error_button.addEventListener("click", () => {
                      error_button.parentElement.style.display="none";
                  });
                </script>
              </div>
              % if request.session.peek_flash('error'):
                <% flash = request.session.pop_flash('error') %>
                % for message in flash:
                <div class="alert alert-danger alert-dismissible">
                  ${message}
                  <button
                    type="button"
                    class="btn-close"
                    data-bs-dismiss="alert"
                    aria-label="Close"
                  ></button>
                </div>
                % endfor
              % endif
              % if request.session.peek_flash():
                <% flash = request.session.pop_flash() %>
                % for message in flash:
                  <div class="alert alert-success alert-dismissible">
                    ${message}
                    <button
                      type="button"
                      class="btn-close"
                      data-bs-dismiss="alert"
                      aria-label="Close"
                    ></button>
                  </div>
                % endfor
              % endif
            </div>
            <div>${self.body()}</div>
          </div>
        </div>
      </main>
    </div>
  </body>
</html>
