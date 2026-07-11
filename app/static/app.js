(function () {
  const state = { calYear: 0, calMonth: 0, configLoaded: false, run: null, runId: "", selectedDate: "", timer: null };
  const stepNames = ["scraping", "rewriting", "formatting", "cover", "done"];
  const $ = (id) => document.getElementById(id);
  const pad = (value) => String(value).padStart(2, "0");
  const dateValue = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const dateLabel = (date) => `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}`;
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const monthNames = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"];

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "请求失败");
    return payload;
  }

  function renderCalendar(year, month) {
    const now = new Date();
    state.calYear = year === undefined ? now.getFullYear() : year;
    state.calMonth = month === undefined ? now.getMonth() : month;
    $("calMonth").textContent = `${monthNames[state.calMonth]} ${state.calYear}`;
    $("calToday").textContent = dateLabel(now);

    const grid = $("calGrid");
    grid.replaceChildren();
    ["日", "一", "二", "三", "四", "五", "六"].forEach((label) => grid.appendChild(node("div", "w", label)));
    const firstDay = new Date(state.calYear, state.calMonth, 1).getDay();
    const days = new Date(state.calYear, state.calMonth + 1, 0).getDate();
    for (let index = 0; index < firstDay; index += 1) grid.appendChild(node("div", "d empty"));
    for (let day = 1; day <= days; day += 1) {
      const value = `${state.calYear}-${pad(state.calMonth + 1)}-${pad(day)}`;
      const button = node("button", "d", String(day));
      button.type = "button";
      button.dataset.date = value;
      if (value === dateValue(now)) button.classList.add("today");
      if (value === state.selectedDate) button.classList.add("sel");
      button.addEventListener("click", () => pickDate(value));
      grid.appendChild(button);
    }
    if (!state.selectedDate) pickDate(dateValue(now));
  }

  function pickDate(value) {
    state.selectedDate = value;
    document.querySelectorAll(".cal-grid .d").forEach((element) => element.classList.toggle("sel", element.dataset.date === value));
    const selected = new Date(`${value}T00:00:00`);
    $("fetchDate").textContent = dateLabel(selected);
    $("fetchWeekday").textContent = weekdays[selected.getDay()];
    $("btnFetch").disabled = false;
    if (!state.configLoaded) return;
    const title = `AI 行业热点新闻 | ${value}`;
    $("inputTitle").value = title;
    saveSettings({ title });
  }

  function setStep(step, className, message) {
    const element = document.querySelector(`.tl-step[data-step="${step}"]`);
    if (!element) return;
    element.className = "tl-step";
    if (className) element.classList.add(className);
    if (message !== undefined) element.querySelector(".tl-status").textContent = message;
  }

  function resetProgress() {
    $("errCard").style.display = "none";
    stepNames.forEach((step) => setStep(step, "", "等待中"));
    setStep("scraping", "active", "准备中...");
    $("btnPublish").disabled = true;
    $("pvContent").replaceChildren(node("div", "preview-placeholder", "正在处理，请保持此页面打开…"));
  }

  function applyEvent(event) {
    const stage = event.stage || "";
    const status = event.status || "";
    const message = event.message || "";
    if (stage === "scraping") {
      if (status === "complete") {
        setStep("scraping", "done", "完成");
        setStep("rewriting", "active", "改写中...");
      } else {
        setStep("scraping", "active", message || "抓取中...");
      }
    } else if (stage === "rewriting") {
      setStep("rewriting", "active", message || "改写中...");
    } else if (stage === "formatting" && status === "complete") {
      setStep("rewriting", "done", "完成");
      setStep("formatting", "done", "完成");
      setStep("cover", "active", "生成中...");
    } else if (stage === "cover") {
      setStep("cover", status === "complete" ? "done" : "active", message || "生成中...");
    } else if (stage === "done") {
      setStep("rewriting", "done", "完成");
      setStep("formatting", "done", "完成");
      setStep("cover", "done", "完成");
      setStep("done", "done", "完成");
      $("fetchHint").textContent = "文章已生成，尚未发布";
    } else if (stage === "error") {
      const active = stepNames.find((step) => document.querySelector(`.tl-step[data-step="${step}"]`)?.classList.contains("active"));
      if (active) setStep(active, "fail", message || "失败");
    }
  }

  function setStatus(kind, label, detail) {
    const bar = $("statusBar");
    bar.className = "status-bar";
    if (kind === "done") {
      bar.classList.add("status-done");
      bar.textContent = "✓ DONE";
    } else if (kind === "failed") {
      bar.classList.add("status-fail");
      bar.textContent = "FAILED";
    } else if (kind === "running") {
      bar.textContent = "RUNNING...";
    } else {
      bar.textContent = "IDLE";
    }
    $("statusText").textContent = label;
    $("statusDetail").textContent = detail;
  }

  function renderArticle(article) {
    const content = $("pvContent");
    content.replaceChildren();
    if (!article || !article.items) {
      content.appendChild(node("div", "preview-placeholder", "请先选择日期并点击「抓取」"));
      return;
    }
    let category = null;
    article.items.forEach((item) => {
      if (item.category !== category) {
        category = item.category;
        const heading = node("div", "preview-section");
        heading.append(node("span", "label", category || "今日资讯"));
        content.appendChild(heading);
      }
      const entry = node("article", "preview-item");
      entry.appendChild(node("div", "item-title", item.title || "未命名资讯"));
      entry.appendChild(node("div", "item-body", item.body || ""));
      const source = node("div", "source", `来源：${item.source || "原始链接"} `);
      if (item.source_url) {
        const link = node("a", "", "查看原文");
        link.href = item.source_url;
        link.target = "_blank";
        link.rel = "noreferrer";
        source.appendChild(link);
      }
      entry.appendChild(source);
      content.appendChild(entry);
    });
  }

  function renderCover(article) {
    const image = $("coverPreviewImg");
    if (!article?.cover_url) {
      image.removeAttribute("src");
      image.alt = "文章生成完成后会显示封面";
      return;
    }
    image.src = `${article.cover_url}?t=${Date.now()}`;
    image.alt = "日报封面预览";
  }

  function renderRun(run) {
    if (run.state === "published" && !run.article) {
      stopPolling();
      state.run = null;
      state.runId = "";
      localStorage.removeItem("ai-daily-run-id");
      renderArticle(null);
      renderCover(null);
      $("btnFetch").disabled = false;
      $("btnPublish").disabled = true;
      $("cornerTag").classList.remove("show");
      $("cornerBadge").textContent = "DONE";
      $("fetchHint").textContent = "微信草稿已创建，本地内容已清理";
      setStatus("done", "微信草稿已创建，本地内容已清理", `草稿回执：${run.media_id || "已记录"}`);
      return;
    }
    state.run = run;
    state.runId = run.id || state.runId;
    if (run.id) localStorage.setItem("ai-daily-run-id", run.id);
    resetProgress();
    (run.events || []).forEach(applyEvent);
    const active = ["queued", "scraping", "rewriting", "publishing"].includes(run.state);
    $("btnFetch").disabled = active;
    $("cornerTag").classList.toggle("show", active || run.state === "failed");

    if (run.state === "ready") {
      applyEvent({ stage: "done", status: "complete" });
      renderArticle(run.article);
      renderCover(run.article);
      $("btnPublish").disabled = false;
      $("cornerBadge").textContent = "READY";
      setStatus("done", "文章已生成，尚未发布", "可先预览或复制；确认后再创建微信公众号草稿。");
    } else if (run.state === "published") {
      renderArticle(run.article);
      renderCover(run.article);
      $("btnPublish").disabled = true;
      $("cornerBadge").textContent = "DONE";
      setStatus("done", "微信草稿已创建", `草稿回执：${run.media_id || "已记录"}`);
    } else if (run.state === "failed") {
      $("errCard").style.display = "";
      $("errText").textContent = run.error || "处理失败";
      $("cornerBadge").textContent = "FAIL";
      setStatus("failed", "运行失败", run.error || "请检查错误后重新抓取");
    } else if (active) {
      const latest = run.events?.at(-1)?.message || "正在处理";
      $("cornerBadge").textContent = "BUSY";
      setStatus("running", "正在处理…", `${latest} 全量内容按批并行改写，通常约 1–2 分钟。`);
    } else {
      $("cornerTag").classList.remove("show");
      setStatus("idle", "等待操作", "选择日期后点击「抓取」开始。");
    }
  }

  function stopPolling() {
    if (state.timer) window.clearTimeout(state.timer);
    state.timer = null;
  }

  async function pollRun() {
    if (!state.runId) return;
    try {
      const run = await requestJson(`/api/runs/${encodeURIComponent(state.runId)}`);
      renderRun(run);
      if (["queued", "scraping", "rewriting", "publishing"].includes(run.state)) {
        state.timer = window.setTimeout(pollRun, 1000);
      } else {
        stopPolling();
      }
    } catch (error) {
      stopPolling();
      localStorage.removeItem("ai-daily-run-id");
      setStatus("failed", "无法读取运行进度", error.message);
    }
  }

  async function restoreRun() {
    const runId = localStorage.getItem("ai-daily-run-id");
    if (!runId) return;
    state.runId = runId;
    const run = await requestJson(`/api/runs/${encodeURIComponent(runId)}`);
    state.selectedDate = run.date;
    const restored = new Date(`${run.date}T00:00:00`);
    renderCalendar(restored.getFullYear(), restored.getMonth());
    renderRun(run);
    if (["queued", "scraping", "rewriting", "publishing"].includes(run.state)) {
      state.timer = window.setTimeout(pollRun, 1000);
    }
  }

  async function saveSettings(values) {
    return requestJson("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
  }

  async function loadSettings() {
    try {
      const values = await requestJson("/api/config");
      if (values.title) $("inputTitle").value = values.title;
      if (values.author !== undefined) $("inputAuthor").value = values.author;
      if (values.max_words) $("inputMaxWords").value = values.max_words;
      if (values.schedule_time) $("scheduleTime").value = values.schedule_time;
    } catch (error) {
      toast(`设置读取失败：${error.message}`, "error");
    } finally {
      state.configLoaded = true;
    }
  }

  async function loadScheduleStatus() {
    try {
      const schedule = await requestJson("/api/schedule");
      if (schedule.installed && schedule.configured === false) {
        toast(schedule.message || "检测到旧定时任务，请点击保存完成更新", "error");
      }
    } catch (error) {
      toast(`定时任务状态读取失败：${error.message}`, "error");
    }
  }

  $("calPrev").addEventListener("click", () => {
    const previous = state.calMonth === 0 ? 11 : state.calMonth - 1;
    renderCalendar(state.calMonth === 0 ? state.calYear - 1 : state.calYear, previous);
  });
  $("calNext").addEventListener("click", () => {
    const next = state.calMonth === 11 ? 0 : state.calMonth + 1;
    renderCalendar(state.calMonth === 11 ? state.calYear + 1 : state.calYear, next);
  });

  $("inputMaxWords").addEventListener("change", () => saveSettings({ max_words: Number($("inputMaxWords").value) || 150 }).catch((error) => toast(error.message, "error")));
  $("inputTitle").addEventListener("change", () => saveSettings({ title: $("inputTitle").value }).catch((error) => toast(error.message, "error")));
  $("inputAuthor").addEventListener("change", () => saveSettings({ author: $("inputAuthor").value }).catch((error) => toast(error.message, "error")));
  $("btnSaveTime").addEventListener("click", async () => {
    try {
      await requestJson("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schedule_time: $("scheduleTime").value }),
      });
      toast("每日定时任务已更新", "success");
    } catch (error) {
      toast(error.message, "error");
    }
  });

  $("btnFetch").addEventListener("click", async () => {
    if (!state.selectedDate) return;
    stopPolling();
    try {
      await saveSettings({
        title: $("inputTitle").value,
        author: $("inputAuthor").value,
        max_words: Number($("inputMaxWords").value) || 150,
      });
      const run = await requestJson("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: state.selectedDate, retry: true }),
      });
      renderRun(run);
      pollRun();
    } catch (error) {
      setStatus("failed", "无法开始生成", error.message);
      toast(error.message, "error");
    }
  });

  document.querySelectorAll(".pv-btn").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".pv-btn").forEach((item) => item.classList.toggle("active", item === button));
      const cover = button.dataset.view === "cover";
      $("pvContent").style.display = cover ? "none" : "";
      $("pvCover").style.display = cover ? "" : "none";
      if (cover) renderCover(state.run?.article);
      else renderArticle(state.run?.article);
    });
  });

  $("btnCopy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("pvContent").innerText);
      toast("已复制到剪贴板", "success");
    } catch (error) {
      toast("复制失败", "error");
    }
  });

  $("btnPublish").addEventListener("click", async () => {
    if (!state.runId) return;
    $("btnPublish").disabled = true;
    try {
      const run = await requestJson(`/api/runs/${encodeURIComponent(state.runId)}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: state.selectedDate }),
      });
      renderRun(run);
      toast("微信草稿已创建", "success");
    } catch (error) {
      $("btnPublish").disabled = false;
      toast(`创建草稿失败：${error.message}`, "error");
    }
  });

  function toast(message, type) {
    const toastBox = $("toastBox");
    const toast = node("div", `toast ${type === "error" ? "error" : "success"}`, message);
    toastBox.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3000);
  }

  renderCalendar();
  loadSettings().then(loadScheduleStatus).then(restoreRun);
  setStatus("idle", "等待操作", "选择日期后点击「抓取」开始。");
})();
