// JSON import page: examples, formatting, file loading and a live syntax check.
(function () {
    var box = document.getElementById("json_text");
    if (!box) { return; }
    var status = document.getElementById("json-status");

    var EXAMPLES = {
        single: {
            date: "2026-09-28", day: "Monday", check_in: "09:00 AM", check_out: "05:00 PM",
            task: "Worked on ball physics and throwing mechanics.", project: "Cup Toss Game",
            domain: "Physics Programming", tools: "Unity, C#, Rigidbody",
            learning: "Learned how Rigidbody physics affects projectile movement."
        },
        multiple: [
            {
                date: "2026-09-28", day: "Monday", check_in: "09:00 AM", check_out: "05:00 PM",
                task: "Worked on ball physics and throwing mechanics.", project: "Cup Toss Game",
                domain: "Physics Programming", tools: "Unity, C#, Rigidbody", learning: "Learned Rigidbody physics."
            },
            {
                date: "2026-09-29", day: "Tuesday", check_in: "09:00 AM", check_out: "05:00 PM",
                task: "Implemented cup collision detection.", project: "Cup Toss Game",
                domain: "Collision Detection", tools: "Unity, C#, Colliders", learning: "Learned collision events."
            }
        ],
        tables: {
            tables: {
                "Attendance": [
                    { date: "2026-09-28", day: "Monday", check_in: "09:00 AM", check_out: "05:00 PM" }
                ],
                "Daily Progress": [
                    {
                        date: "2026-09-28", task: "Worked on ball physics.", project: "Cup Toss Game",
                        domain: "Physics Programming", tools: "Unity, C#, Rigidbody",
                        learning: "Learned Rigidbody physics."
                    }
                ]
            }
        }
    };

    function check() {
        var text = box.value.trim();
        if (!text) { status.textContent = ""; return; }
        try {
            var data = JSON.parse(text);
            var count = Array.isArray(data) ? data.length :
                (data && data.tables ? Object.keys(data.tables).reduce(function (n, k) { return n + [].concat(data.tables[k]).length; }, 0) : 1);
            status.textContent = "✓ Valid JSON syntax (" + count + " record" + (count === 1 ? "" : "s") + ")";
            status.style.color = "#1c7c4a";
        } catch (e) {
            status.textContent = "✗ " + e.message + " (the server will try to repair small problems)";
            status.style.color = "#9a6200";
        }
    }

    box.addEventListener("input", check);
    document.querySelectorAll("[data-example]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            box.value = JSON.stringify(EXAMPLES[btn.getAttribute("data-example")], null, 4);
            check();
        });
    });
    document.getElementById("format-json").addEventListener("click", function () {
        try { box.value = JSON.stringify(JSON.parse(box.value), null, 4); check(); }
        catch (e) { status.textContent = "✗ Cannot format: " + e.message; status.style.color = "#b3261e"; }
    });
    document.getElementById("clear-json").addEventListener("click", function () { box.value = ""; check(); });
    document.getElementById("json-file").addEventListener("change", function (event) {
        var file = event.target.files[0];
        if (!file) { return; }
        if (file.size > 2000000) { status.textContent = "That file is too large."; return; }
        var reader = new FileReader();
        reader.onload = function () { box.value = String(reader.result); check(); };
        reader.readAsText(file);
    });
    check();
})();
