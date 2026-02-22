(function () {
  "use strict";

  function initProfileStatsUpload() {
    var form = document.getElementById("stats-upload-form");
    if (!form) return;

    var dropZone = document.getElementById("stats-drop-zone");
    var input = document.getElementById("stats-files-input");
    var statusEl = document.getElementById("stats-upload-status");
    var summaryBox = document.getElementById("stats-upload-summary");
    var resultsList = document.getElementById("stats-upload-results");
    var selectedBlock = document.getElementById("stats-selected-files");
    var selectedList = document.getElementById("stats-files-list");
    var selectedCount = document.getElementById("stats-files-count");
    var uploadBtn = document.getElementById("stats-upload-btn");
    var uploadUrl = form.getAttribute("data-upload-url") || "/profile/stats/upload/";

    var files = [];

    function setStatus(text, tone) {
      statusEl.textContent = text || "";
      statusEl.className = "text-sm";
      if (tone === "error") {
        statusEl.classList.add("text-red-400");
      } else if (tone === "success") {
        statusEl.classList.add("text-green-400");
      } else {
        statusEl.classList.add("text-gray-400");
      }
    }

    function renderSelectedFiles() {
      selectedList.innerHTML = "";
      if (!files.length) {
        selectedBlock.classList.add("hidden");
        selectedCount.textContent = "0";
        return;
      }

      selectedBlock.classList.remove("hidden");
      selectedCount.textContent = String(files.length);

      files.forEach(function (file, idx) {
        var li = document.createElement("li");
        li.className = "flex items-center justify-between gap-2";

        var name = document.createElement("span");
        name.className = "truncate";
        name.textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";

        var removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "text-red-400 hover:text-red-300";
        removeBtn.textContent = "Удалить";
        removeBtn.addEventListener("click", function () {
          files.splice(idx, 1);
          renderSelectedFiles();
        });

        li.appendChild(name);
        li.appendChild(removeBtn);
        selectedList.appendChild(li);
      });
    }

    function addFiles(newFiles) {
      Array.prototype.forEach.call(newFiles, function (file) {
        var duplicate = files.some(function (f) {
          return f.name === file.name && f.size === file.size;
        });
        if (!duplicate) {
          files.push(file);
        }
      });
      renderSelectedFiles();
    }

    function onDrop(event) {
      event.preventDefault();
      dropZone.classList.remove("border-red-500");
      addFiles(event.dataTransfer.files || []);
    }

    dropZone.addEventListener("click", function () {
      input.click();
    });
    dropZone.addEventListener("dragover", function (event) {
      event.preventDefault();
      dropZone.classList.add("border-red-500");
    });
    dropZone.addEventListener("dragleave", function () {
      dropZone.classList.remove("border-red-500");
    });
    dropZone.addEventListener("drop", onDrop);

    input.addEventListener("change", function (event) {
      addFiles(event.target.files || []);
      input.value = "";
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      if (!files.length) {
        setStatus("Выберите хотя бы один файл.", "error");
        return;
      }

      var csrfInput = form.querySelector("input[name='csrfmiddlewaretoken']");
      var csrfToken = csrfInput ? csrfInput.value : "";
      var formData = new FormData();
      if (csrfToken) {
        formData.append("csrfmiddlewaretoken", csrfToken);
      }
      files.forEach(function (file) {
        formData.append("files", file);
      });

      uploadBtn.disabled = true;
      uploadBtn.classList.add("opacity-60", "cursor-not-allowed");
      setStatus("Загрузка и обработка файлов...", "info");

      fetch(uploadUrl, {
        method: "POST",
        body: formData,
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      })
        .then(function (resp) {
          return resp.json().then(function (data) {
            return { ok: resp.ok, status: resp.status, data: data };
          });
        })
        .then(function (payload) {
          var data = payload.data || {};
          if (!payload.ok || data.success === false) {
            throw new Error(data.error || ("Ошибка сервера (" + payload.status + ")"));
          }

          var summary = data.summary || {};
          summaryBox.classList.remove("hidden");
          document.getElementById("sum-processed").textContent = String(summary.processed || 0);
          document.getElementById("sum-created").textContent = String(summary.created || 0);
          document.getElementById("sum-duplicates").textContent = String(summary.duplicates || 0);
          document.getElementById("sum-errors").textContent = String(summary.errors || 0);

          resultsList.innerHTML = "";
          (data.results || []).forEach(function (item) {
            var li = document.createElement("li");
            var status = item.status || "error";
            if (status === "created") {
              li.className = "text-green-300";
              li.textContent = item.file + ": добавлен (" + (item.rows_created || 0) + " строк)";
            } else if (status === "duplicate") {
              li.className = "text-amber-300";
              li.textContent = item.file + ": дубликат (пропущено " + (item.rows_duplicates || 0) + " строк)";
            } else {
              li.className = "text-red-300";
              li.textContent = item.file + ": " + (item.error || "ошибка");
            }
            resultsList.appendChild(li);
          });

          files = [];
          renderSelectedFiles();
          setStatus("Обработка завершена.", "success");

          if ((summary.created || 0) > 0) {
            window.setTimeout(function () {
              window.location.reload();
            }, 1200);
          }
        })
        .catch(function (err) {
          setStatus(err.message || "Ошибка загрузки.", "error");
        })
        .finally(function () {
          uploadBtn.disabled = false;
          uploadBtn.classList.remove("opacity-60", "cursor-not-allowed");
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initProfileStatsUpload);
  } else {
    initProfileStatsUpload();
  }
})();
