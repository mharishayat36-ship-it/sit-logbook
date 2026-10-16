// Editable records table (extraction preview and weekly preview).
(function () {
    var editor = document.getElementById("editor");
    if (!editor) { return; }
    var body = document.getElementById("records-body");
    var saveUrl = editor.getAttribute("data-save-url");
    var saveState = document.getElementById("save-state");
    var errorBox = document.getElementById("editor-errors");
    var jsonView = document.getElementById("json-view");
    var dirty = false;
    var pendingSave = null;

    var FIELDS = ["date", "day", "check_in", "check_out", "task", "project", "domain", "tools", "learning", "notes"];
    var EXPORT_FIELDS = FIELDS.slice(0, 9);

    function collect() {
        var records = [];
        body.querySelectorAll("tr").forEach(function (tr) {
            var rec = {};
            tr.querySelectorAll("[data-field]").forEach(function (el) {
                rec[el.getAttribute("data-field")] = el.value.trim();
            });
            records.push(rec);
        });
        return records;
    }

    function exportJson() {
        var records = collect();
        var fields = EXPORT_FIELDS.slice();
        if (records.some(function (r) { return r.notes; })) { fields.push("notes"); }
        return JSON.stringify(records.map(function (r) {
            var o = {};
            fields.forEach(function (f) { o[f] = r[f] || ""; });
            return o;
        }), null, 4);
    }

    function refreshView() { if (jsonView) { jsonView.value = exportJson(); } }

    function setDirty(value) {
        dirty = value;
        saveState.textContent = value ? "Unsaved changes" : saveState.textContent;
        saveState.style.color = value ? "#9a6200" : "";
        refreshView();
    }

    body.addEventListener("input", function () { setDirty(true); });
    body.addEventListener("click", function (event) {
        var btn = event.target.closest(".delete-row");
        if (btn) { btn.closest("tr").remove(); setDirty(true); }
    });
    document.getElementById("add-row").addEventListener("click", function () {
        var tpl = document.getElementById("row-template");
        body.appendChild(tpl.content.cloneNode(true));
        setDirty(true);
        var last = body.lastElementChild;
        if (last) { var first = last.querySelector("input"); if (first) { first.focus(); } }
    });

    function showRows(rows) {
        var trs = body.querySelectorAll("tr");
        rows.forEach(function (row, i) {
            var tr = trs[i];
            if (!tr) { return; }
            tr.className = row.status === "ok" ? "" : "row-" + row.status;
            var cell = tr.querySelector(".status-cell");
            var label = { ok: "Valid", warning: "Warning", error: "Error" }[row.status];
            cell.innerHTML = "";
            var badge = document.createElement("span");
            badge.className = "badge " + row.status;
            badge.textContent = label;
            cell.appendChild(badge);
            var msg = document.createElement("div");
            msg.className = "small muted msg-cell";
            row.messages.forEach(function (m) {
                msg.appendChild(document.createTextNode(m.text));
                msg.appendChild(document.createElement("br"));
            });
            cell.appendChild(msg);
        });
    }

    // Returns a promise that resolves true when the server accepted the data.
    function save() {
        if (pendingSave) { return pendingSave; }
        errorBox.innerHTML = "";
        saveState.textContent = "Saving...";
        editor.setAttribute("aria-busy", "true");
        var records = collect();
        var controls = editor.querySelectorAll("input, textarea, button");
        controls.forEach(function (control) { control.disabled = true; });
        pendingSave = fetch(saveUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content },
            body: JSON.stringify({ records: records })
        }).then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
          .then(function (res) {
            if (res.data.rows) { showRows(res.data.rows); }
            if (res.ok && res.data.ok) {
                // Display the canonical values returned by the server, including
                // corrected weekdays and normalized times, before copying JSON.
                var trs = body.querySelectorAll("tr");
                res.data.rows.forEach(function (row, i) {
                    if (trs[i] && row.record) {
                        trs[i].querySelectorAll("[data-field]").forEach(function (el) {
                            el.value = row.record[el.getAttribute("data-field")] || "";
                        });
                    }
                });
                dirty = false;
                refreshView();
                saveState.textContent = "Saved (" + res.data.count + " records)";
                saveState.style.color = "#1c7c4a";
                return true;
            }
            saveState.textContent = "";
            var div = document.createElement("div");
            div.className = "notice error";
            div.textContent = res.data.error || "The changes could not be saved.";
            errorBox.appendChild(div);
            return false;
        }).catch(function () {
            saveState.textContent = "";
            var div = document.createElement("div");
            div.className = "notice error";
            div.textContent = "Could not reach the server.";
            errorBox.appendChild(div);
            return false;
        }).finally(function () {
            pendingSave = null;
            editor.setAttribute("aria-busy", "false");
            controls.forEach(function (control) { control.disabled = false; });
        });
        return pendingSave;
    }

    document.getElementById("save-changes").addEventListener("click", save);

    // Buttons/links that must use the latest edits: save first, then continue.
    document.querySelectorAll("[data-export-url]").forEach(function (link) {
        link.addEventListener("click", function (event) {
            event.preventDefault();
            var url = link.getAttribute("data-export-url");
            (dirty ? save() : Promise.resolve(true)).then(function (ok) { if (ok) { window.location = url; } });
        });
    });
    document.querySelectorAll("form.needs-save").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (form.dataset.waiting) { event.preventDefault(); return; }
            if (!dirty && !pendingSave) { return; }
            event.preventDefault();
            form.dataset.waiting = "true";
            save().then(function (ok) {
                delete form.dataset.waiting;
                if (ok) { form.requestSubmit(); }
            });
        });
    });

    var copyBtn = document.getElementById("copy-json");
    if (copyBtn) {
        copyBtn.addEventListener("click", function () {
            var text = exportJson();
            var done = function () { copyBtn.textContent = "Copied!"; setTimeout(function () { copyBtn.textContent = "Copy JSON"; }, 1500); };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(done).catch(function () {
                    saveState.textContent = "Clipboard unavailable. Select and copy the JSON below.";
                    if (jsonView) { jsonView.focus(); jsonView.select(); }
                });
            } else {
                refreshView(); jsonView.select(); document.execCommand("copy"); done();
            }
        });
    }
    var dlBtn = document.getElementById("download-json");
    if (dlBtn) {
        dlBtn.addEventListener("click", function () {
            var blob = new Blob([exportJson()], { type: "application/json" });
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "logbook_records.json";
            document.body.appendChild(a); a.click(); a.remove();
            setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
        });
    }

    window.addEventListener("beforeunload", function (event) {
        if (dirty) { event.preventDefault(); event.returnValue = ""; }
    });
    refreshView();
})();
