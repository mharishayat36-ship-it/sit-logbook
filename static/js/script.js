// General page behaviour shared by every page.
document.addEventListener("DOMContentLoaded", function () {
    // Dismiss flash messages.
    document.querySelectorAll(".flash-close").forEach(function (btn) {
        btn.addEventListener("click", function () { btn.closest(".flash").remove(); });
    });

    // <form data-confirm="Are you sure?"> asks before submitting.
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!window.confirm(form.getAttribute("data-confirm"))) { event.preventDefault(); }
        });
    });

    // Disable submit buttons after the first click so big operations are not run twice.
    document.querySelectorAll("form[data-once]").forEach(function (form) {
        form.addEventListener("submit", function () {
            form.querySelectorAll("button[type=submit]").forEach(function (b) {
                setTimeout(function () { b.disabled = true; }, 0);
            });
        });
    });

    // Daily entry page: fill in the weekday and week information when the date changes.
    var dateInput = document.getElementById("date");
    var info = document.getElementById("date-info");
    var dayInput = document.getElementById("day");
    if (dateInput && info && dayInput) {
        var update = function () {
            if (!dateInput.value) { info.textContent = ""; return; }
            fetch("/api/day-info?date=" + encodeURIComponent(dateInput.value))
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d.ok) { info.textContent = d.error || ""; return; }
                    dayInput.value = d.day;
                    info.textContent = "Week " + d.week + " — " + d.day + " — " + d.reason;
                    info.className = "hint";
                });
        };
        dateInput.addEventListener("change", update);
        if (dateInput.value) { update(); }
    }

    // Weekly report page: show the working days of the chosen week.
    var weekInput = document.getElementById("week");
    var weekInfo = document.getElementById("week-info");
    if (weekInput && weekInfo) {
        var showWeek = function () {
            var w = parseInt(weekInput.value, 10);
            if (!w) { weekInfo.textContent = ""; return; }
            fetch("/api/week-info?week=" + w)
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d.ok) { weekInfo.textContent = d.error; return; }
                    weekInfo.textContent = "Week " + d.week + ": " + d.count + " working days" +
                        (d.saturday ? " (Monday–Saturday)" : " (Monday–Friday)") + " — " +
                        d.days.map(function (x) { return x.day.substring(0, 3) + " " + x.label.replace(/ \d{4}$/, ""); }).join(", ");
                });
        };
        weekInput.addEventListener("input", showWeek);
        if (weekInput.value) { showWeek(); }
    }

    // Mapping page: add a blank row.
    var addBtn = document.getElementById("add-mapping-row");
    if (addBtn) {
        addBtn.addEventListener("click", function () {
            var body = document.getElementById("mapping-body");
            var template = document.getElementById("mapping-row-template");
            var index = body.querySelectorAll("tr").length;
            var html = template.innerHTML.replace(/__INDEX__/g, index);
            body.insertAdjacentHTML("beforeend", html);
        });
    }
});
