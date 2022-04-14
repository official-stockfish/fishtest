// https://stackoverflow.com/questions/14267781/sorting-html-table-with-javascript
// https://stackoverflow.com/questions/40201533/sort-version-dotted-number-strings-in-javascript
const getCellValue = (tr, idx) => tr.children[idx].dataset.diff || tr.children[idx].innerText || tr.children[idx].textContent;
const padDotVersion = (dn) => dn.split('.').map(n => +n+1000).join('');
const padDotVersionStr = (dn) => dn.replace(/\d+/g, n => +n+1000);
let p1, p2;
const comparer = (idx, asc) => (a, b) => ((v1, v2) =>
    v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2)
    ? v1 - v2
    : v1 !== '' && v2 !== '' && !isNaN('0x' + v1) && !isNaN('0x' + v2)
    ? parseInt(v1, 16) - parseInt(v2, 16)
    : v1 !== '' && v2 !== '' && !isNaN(p1 = padDotVersion(v1)) && !isNaN(p2 = padDotVersion(v2))
    ? p1 - p2
    : v1 !== '' && v2 !== '' && !isNaN(padDotVersion(v1.replace('clang++ ', '').replace('g++ ', ''))) && !isNaN(padDotVersion(v2.replace('clang++ ', '').replace('g++ ', '')))
    ? padDotVersionStr(v1).toString().localeCompare(padDotVersionStr(v2))
    : v1.toString().localeCompare(v2)
)(getCellValue(asc ? a : b, idx), getCellValue(asc ? b : a, idx));

$(() => {
    // clicking on table headers sorts the rows
    $(document).on('click', 'th', (event) => {
        const th = $(event.currentTarget)[0];
        const table = th.closest('table');
        const body = table.querySelector('tbody');
        Array.from(body.querySelectorAll('tr'))
            .sort(comparer(Array.from(th.parentNode.children).indexOf(th), this.asc = !this.asc))
            .forEach(tr => body.appendChild(tr));
    });


    $("#non_default-button").click(function() {
        var active = $(this).text().trim().substring(0, 4) === 'Hide';
        $(this).text(active ? 'Show non default nets' : 'Hide non default nets');
        $.cookie('non_default_state', active ? 'Hide' : 'Show', {expires: 3650});
        window.location.reload();
    });

    let fetchingMachines = false;
    $("#machines-button").click(function() {
        const active = $(this).text().trim() === 'Hide';
        $(this).text(active ? 'Show' : 'Hide');
        if (!active && !$("#machines table")[0] && !fetchingMachines) {
            fetchingMachines = true;
            $.get("/tests/machines", (html) => $("#machines").append(html));
        }
        $("#machines").slideToggle(150);
        $.cookie('machines_state', $(this).text().trim(), {expires: 3650});
    });

    $("#tasks-button").click(function() {
        const active = $(this).text().trim() === 'Hide';
        $(this).text(active ? 'Show' : 'Hide');
        $("#tasks").slideToggle(150);
        $.cookie('tasks_state', $(this).text().trim(), {expires: 3650});
    });

    // Click the sun/moon icons to change the color theme of the site
    // SRI hash for "fishtest/server/fishtest/static/css/theme.dark.css":
    // openssl dgst -sha256 -binary theme.dark.css | openssl base64 -A
    let theme = $.cookie('theme') || 'light';
    $("#change-color-theme").click(function() {
      if (theme === 'light') {
        const darkThemeSha256 = $("meta[name='dark-theme-sha256']").attr("content");
        $("#sun").show();
        $("#moon").hide();
        $("<link>")
          .attr("href", "/css/theme.dark.css?v=" + darkThemeSha256)
          .attr("rel", "stylesheet")
          .attr("integrity", "sha256-" + darkThemeSha256)
          .appendTo($("head"));
        theme = 'dark';
      } else {
        $("#sun").hide();
        $("#moon").show();
        $('head link[href*="/css/theme.dark.css"]').remove();
        theme = 'light';
      }
      let cookieExpireDate = new Date();
      // Remember the theme for 30 days
      cookieExpireDate.setTime(cookieExpireDate.getTime() + 30 * 24 * 60 * 60 * 1000);
      $.cookie('theme', theme, {
        path: '/',
        expires: cookieExpireDate,
      });
    });

    // CSRF protection for links and forms
    const csrfToken = $("meta[name='csrf-token']").attr('content');
    $("#logout").on("click", (event) => {
        event.preventDefault();
        $.ajax({
            url: "/logout",
            method: "POST",
            headers: {
                'X-CSRF-Token': csrfToken
            },
            success: () => {
                window.location = "/";
            }
        });
    });
    $("form[method='POST']").each((i, $form) => {
        $("<input>")
            .attr("type", "hidden")
            .attr("name", "csrf_token").val(csrfToken)
            .appendTo($form);
    });
});
