const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appScript = fs.readFileSync(path.resolve(__dirname, "../static/app.js"), "utf8");

class Element {
  constructor(id = "") {
    this.id = id;
    this.style = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.innerText = "";
    this.disabled = false;
    this.children = [];
    this.listeners = {};
    this.classList = { add() {}, remove() {}, toggle() {} };
  }

  addEventListener(event, listener) { this.listeners[event] = listener; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  replaceChildren(...children) { this.children = children; }
  removeAttribute(name) { delete this[name]; }
  remove() {}
  querySelector() { return null; }
}

function response(status, payload) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

async function flush() {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

async function runScenario(publishOutcome, publish = true) {
  const elements = new Map();
  const timers = [];
  const storage = new Map([["ai-daily-run-id", "run-1"]]);
  const requests = [];
  let phase = "restore";

  const document = {
    createElement: () => new Element(),
    getElementById: (id) => {
      if (!elements.has(id)) elements.set(id, new Element(id));
      return elements.get(id);
    },
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const window = {
    setTimeout(callback, delay) {
      timers.push({ callback, delay });
      return timers.length;
    },
    clearTimeout() {},
  };
  const readyRun = {
    id: "run-1", date: "2026-07-10", state: "ready", media_id: "", error: "",
    article: {
      opening: "Opening observation",
      closing: "Closing comment",
      items: [{ category: "Model group", title: "Story", body: "Body", source: "Source" }],
    }, events: [],
  };
  const finalizingRun = {
    id: "run-1", date: "2026-07-10", state: "finalizing", media_id: "", error: "",
    article: null, events: [],
  };
  const cleaningRun = {
    id: "run-1", date: "2026-07-10", state: "cleaning", media_id: "", error: "",
    article: null, events: [],
  };
  const context = {
    console,
    Date,
    Promise,
    encodeURIComponent,
    document,
    window,
    navigator: { clipboard: { writeText: async () => {} } },
    localStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    },
    fetch: async (url, options = {}) => {
      const method = options.method || "GET";
      requests.push({ url, method });
      if (url === "/api/config") return response(method === "GET" ? 200 : 200, { title: "Daily", max_words: 150 });
      if (url === "/api/schedule") return response(200, { installed: true });
      if (url.includes("/publish")) {
        phase = "published";
        if (publishOutcome === "failed") return response(502, { error: "publisher unavailable" });
        return response(200, publishOutcome === "finalizing" ? finalizingRun : { ...finalizingRun, state: "published" });
      }
      if (url === "/api/runs/run-1") {
        if (phase === "restore" && publishOutcome === "cleaning") {
          phase = "poll-after-cleaning";
          return response(200, cleaningRun);
        }
        if (phase === "restore") return response(200, readyRun);
        if (phase === "published" && publishOutcome === "finalizing") {
          phase = "poll-after-finalizing";
          return response(200, finalizingRun);
        }
        if (phase === "poll-after-finalizing") return response(404, { error: "run deleted" });
        if (phase === "poll-after-cleaning") return response(404, { error: "run deleted" });
      }
      throw new Error(`unexpected request ${method} ${url}`);
    },
  };

  vm.createContext(context);
  vm.runInContext(appScript, context, { filename: "app.js" });
  await flush();
  if (publish) {
    await elements.get("btnPublish").listeners.click();
    await flush();
  }
  return { elements, requests, storage, timers };
}

(async () => {
  const finalizing = await runScenario("finalizing");
  assert.equal(finalizing.elements.get("statusText").textContent, "微信草稿已创建");
  const pollTimer = finalizing.timers.find((timer) => timer.delay === 1000);
  assert.ok(pollTimer, "finalizing publish must schedule a progress poll");
  await pollTimer.callback();
  await flush();
  assert.equal(finalizing.requests.filter((request) => request.url === "/api/runs/run-1").length, 3);
  assert.equal(finalizing.storage.get("ai-daily-run-id"), undefined);
  assert.equal(finalizing.elements.get("btnFetch").disabled, false);
  assert.equal(finalizing.elements.get("statusText").textContent, "等待操作");

  const published = await runScenario("published");
  assert.equal(published.storage.get("ai-daily-run-id"), undefined);
  assert.equal(published.timers.some((timer) => timer.delay === 1000), false);

  const failed = await runScenario("failed");
  assert.equal(failed.elements.get("btnPublish").disabled, false);
  assert.equal(failed.storage.get("ai-daily-run-id"), "run-1");
  assert.equal(failed.timers.some((timer) => timer.delay === 1000), false);

  const cleaning = await runScenario("cleaning", false);
  const cleaningPoll = cleaning.timers.find((timer) => timer.delay === 1000);
  assert.ok(cleaningPoll, "history cleanup must keep polling until the run disappears");
  await cleaningPoll.callback();
  await flush();
  assert.equal(cleaning.storage.get("ai-daily-run-id"), undefined);
  assert.equal(cleaning.elements.get("btnFetch").disabled, false);

  const editorial = await runScenario("published", false);
  const preview = editorial.elements.get("pvContent").children;
  assert.equal(preview[0].className, "editor-comment", "opening must render before categories");
  assert.equal(preview[0].children[0].textContent, "\u4eca\u65e5\u89c2\u5bdf");
  assert.equal(preview[0].children[1].textContent, "Opening observation");
  assert.equal(preview[3].className, "editor-comment", "closing must render after all news");
  assert.equal(preview[3].children[0].textContent, "\u5c0f\u7f16\u77ed\u8bc4");
  assert.equal(preview[3].children[1].textContent, "Closing comment");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
