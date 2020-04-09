const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;

const comparer = (idx, asc) => (a, b) => ((v1, v2) =>
    v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2) ? v1 - v2 : v1.toString().localeCompare(v2)
)(getCellValue(asc ? a : b, idx), getCellValue(asc ? b : a, idx));

$(() => {
    // clicking on table headers sorts the rows
    document.querySelectorAll('th').forEach(th => {
        th.addEventListener('click', (() => {
            const table = th.closest('table');
            const body = table.querySelector('tbody');
            Array.from(body.querySelectorAll('tr'))
                .sort(comparer(Array.from(th.parentNode.children).indexOf(th), this.asc = !this.asc))
                .forEach(tr => body.appendChild(tr));
        }));
    });

    // clicking Show/Hide on Pending tests and Machines sections toggles them
    $("#pending-button").click(function () {
        var active = $(this).text().trim() === 'Hide';
        $(this).text(active ? 'Show' : 'Hide');
        $("#pending").slideToggle(150);
        $.cookie('pending_state', $(this).text().trim());
    });

    $("#machines-button").click(function () {
        var active = $(this).text().trim() === 'Hide';
        $(this).text(active ? 'Show' : 'Hide');
        $("#machines").toggle();
        $.cookie('machines_state', $(this).text().trim());
    });
});
