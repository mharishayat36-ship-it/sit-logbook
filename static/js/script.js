// Shared workspace interactions. No network dependencies.
document.addEventListener('DOMContentLoaded', function () {
    var menu = document.getElementById('menu-toggle');
    var sidebar = document.getElementById('sidebar');
    var main = document.querySelector('main');
    var topbar = document.querySelector('.topbar');
    var mobile = window.matchMedia('(max-width: 960px)');
    function setMenu(open, focus) {
        document.body.classList.toggle('nav-open', open);
        menu.setAttribute('aria-expanded', String(open));
        menu.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
        sidebar.inert = mobile.matches && !open;
        main.inert = open;
        topbar.inert = open;
        if (open) { sidebar.querySelector('a').focus(); }
        else if (focus) { menu.focus(); }
    }
    menu.addEventListener('click', function () { setMenu(!document.body.classList.contains('nav-open'), true); });
    document.querySelector('.scrim').addEventListener('click', function () { setMenu(false, true); });
    mobile.addEventListener('change', function () { setMenu(false, false); });
    setMenu(false, false);
    document.addEventListener('keydown', function (event) {
        if (!document.body.classList.contains('nav-open')) { return; }
        if (event.key === 'Escape') { setMenu(false, true); }
        if (event.key === 'Tab') {
            var links = sidebar.querySelectorAll('a, button');
            var first = links[0], last = links[links.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
    });
    document.querySelectorAll('.nav a.active').forEach(function (a) { a.setAttribute('aria-current', 'page'); });
    document.querySelectorAll('.table-wrap').forEach(function (table) {
        table.tabIndex = 0;
        table.setAttribute('role', 'region');
        table.setAttribute('aria-label', 'Scrollable data table');
    });
    document.querySelectorAll('.flash-close').forEach(function (btn) {
        btn.addEventListener('click', function () { btn.closest('.flash').remove(); });
    });
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!window.confirm(form.getAttribute('data-confirm'))) { event.preventDefault(); }
        });
    });
    document.querySelectorAll('form[data-once]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (event.defaultPrevented) { return; }
            if (form.dataset.submitting) { event.preventDefault(); return; }
            form.dataset.submitting = 'true';
            // Delay until the browser has included the clicked button's name/value.
            setTimeout(function () {
                form.setAttribute('aria-busy', 'true');
                form.querySelectorAll('button[type=submit]').forEach(function (button) {
                    button.disabled = true;
                    button.dataset.originalLabel = button.textContent;
                    if (button === event.submitter) { button.textContent = 'Working...'; }
                });
            }, 0);
        });
    });
    window.addEventListener('pageshow', function () {
        document.querySelectorAll('form[data-once]').forEach(function (form) {
            delete form.dataset.submitting;
            form.removeAttribute('aria-busy');
            form.querySelectorAll('button[type=submit]').forEach(function (button) {
                button.disabled = false;
                if (button.dataset.originalLabel) { button.textContent = button.dataset.originalLabel; }
            });
        });
    });
    var changedForms = new Set();
    document.querySelectorAll('form[data-dirty-guard]').forEach(function (form) {
        form.addEventListener('input', function () { changedForms.add(form); });
        form.addEventListener('submit', function (event) { if (!event.defaultPrevented) { changedForms.delete(form); } });
    });
    window.addEventListener('beforeunload', function (event) {
        if (changedForms.size) { event.preventDefault(); event.returnValue = ''; }
    });

    // Ignore stale responses when the date/week changes while a request is in flight.
    function bindInfo(input, output, url, render) {
        if (!input || !output) { return; }
        var controller, timer;
        function update() {
            clearTimeout(timer);
            if (controller) { controller.abort(); }
            if (!input.value) { output.textContent = ''; return; }
            timer = setTimeout(function () {
                controller = new AbortController();
                fetch(url + encodeURIComponent(input.value), { signal: controller.signal })
                    .then(function (r) { return r.json(); })
                    .then(function (data) { output.textContent = data.ok ? render(data) : data.error; })
                    .catch(function (error) { if (error.name !== 'AbortError') { output.textContent = 'Could not load calendar details. Please try again.'; } });
            }, 150);
        }
        input.addEventListener('input', update);
        if (input.value) { update(); }
    }
    bindInfo(document.getElementById('date'), document.getElementById('date-info'), '/api/day-info?date=', function (d) {
        document.getElementById('day').value = d.day;
        return 'Week ' + d.week + ' · ' + d.day + ' · ' + d.reason;
    });
    bindInfo(document.getElementById('week'), document.getElementById('week-info'), '/api/week-info?week=', function (d) {
        return 'Week ' + d.week + ': ' + d.count + ' working days (' + (d.saturday ? 'Monday–Saturday' : 'Monday–Friday') + ') · ' + d.days.map(function (x) { return x.label.replace(/ \d{4}$/, ''); }).join(', ');
    });

    var search = document.getElementById('entry-search');
    var rows = document.querySelectorAll('#entries-body tr');
    if (search && rows.length) {
        var index = Array.from(rows, function (row) { return { row: row, text: row.textContent.toLowerCase() }; });
        function filterEntries() {
            var query = search.value.trim().toLowerCase();
            var count = 0;
            index.forEach(function (item) { var visible = item.text.includes(query); item.row.hidden = !visible; if (visible) { count++; } });
            document.getElementById('entry-count').textContent = 'Showing ' + count + ' of ' + rows.length + ' entries';
            document.getElementById('search-empty').hidden = count > 0;
        }
        search.addEventListener('input', filterEntries);
        document.getElementById('clear-search').addEventListener('click', function () { search.value = ''; filterEntries(); search.focus(); });
    }
    var addMapping = document.getElementById('add-mapping-row');
    if (addMapping) {
        addMapping.addEventListener('click', function () {
            var body = document.getElementById('mapping-body');
            var html = document.getElementById('mapping-row-template').innerHTML.replace(/__INDEX__/g, body.querySelectorAll('tr').length);
            body.insertAdjacentHTML('beforeend', html);
            body.lastElementChild.querySelector('input,select').focus();
        });
    }
    document.querySelectorAll('input[type=file][name=document]').forEach(function (input) {
        input.addEventListener('dragover', function () { input.classList.add('drag-over'); });
        ['dragleave', 'drop'].forEach(function (name) { input.addEventListener(name, function () { input.classList.remove('drag-over'); }); });
        input.addEventListener('change', function () {
            input.setCustomValidity('');
            var file = input.files[0];
            if (file && (!/\.docx$/i.test(file.name) || file.size > 16 * 1024 * 1024)) {
                input.setCustomValidity('Choose a Word .docx document no larger than 16 MB.');
                input.reportValidity();
            }
        });
    });
});
