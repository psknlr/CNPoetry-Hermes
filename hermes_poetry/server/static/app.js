/* 诗海赫尔墨斯控制台（原生 JS 单页应用，无构建、无 CDN、离线可用） */
"use strict";

/* ── 昼夜主题 ───────────────────────────────────────────────────── */
(function themeInit() {
  const btn = document.querySelector("#theme-toggle");
  const apply = (t) => {
    if (t === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    btn.textContent = t === "dark" ? "昼" : "夜";
  };
  apply(localStorage.getItem("hermes_theme") || "light");
  btn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    localStorage.setItem("hermes_theme", next);
    apply(next);
  });
})();

const $ = (sel, el) => (el || document).querySelector(sel);
const TOKEN_KEY = "hermes_cnpoetry_token";

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(c));
  }
  return node;
}
const esc = (s) => String(s == null ? "" : s);
/* replaceChildren 会把 null 字符串化——一律经 show() 过滤 */
const show = (box, ...nodes) => box.replaceChildren(...nodes.flat().filter(Boolean));
const errText = (e) => {
  if (e == null) return "";
  if (typeof e === "string") return e;
  let msg = e.message || e.code || JSON.stringify(e);
  if (e.candidates && e.candidates.length)
    msg += "　候选：" + e.candidates.map((c) => c.ref || c.author).join("、");
  return msg;
};

function authHeaders() {
  const t = localStorage.getItem(TOKEN_KEY);
  return t ? { Authorization: "Bearer " + t } : {};
}
const api = {
  async get(path) {
    const r = await fetch(path, { headers: authHeaders() });
    if (r.status === 401) throw new Error("需要令牌：localStorage.setItem('" + TOKEN_KEY + "', '…')");
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body || {}),
    });
    if (r.status === 401) throw new Error("需要令牌：localStorage.setItem('" + TOKEN_KEY + "', '…')");
    return r.json();
  },
};

/* ── poem_id 可点击回源 ─────────────────────────────────────────── */
function linkifyIds(text) {
  const frag = document.createDocumentFragment();
  const re = /CNP_[A-Z0-9]+_\d{5}/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    frag.append(text.slice(last, m.index));
    const pid = m[0];
    frag.append(el("span", { class: "pid", onclick: () => openPoem(pid) }, pid));
    last = m.index + pid.length;
  }
  frag.append(text.slice(last));
  return frag;
}

/* 竖排原文（自右而左，界栏分句）：手工排列不依赖 writing-mode，跨端稳定 */
function vpoem(lines) {
  const cols = lines.map((ln) =>
    el("div", { class: "vcol" }, Array.from(ln).map((ch) => el("span", {}, ch))));
  const inner = el("div", { class: "vpoem" }, cols);
  const wrap = el("div", { class: "vpoem-wrap" }, inner);
  requestAnimationFrame(() => { wrap.scrollLeft = wrap.scrollWidth; });
  return wrap;
}

async function openPoem(ref) {
  const drawer = $("#drawer"), body = $("#drawer-body");
  drawer.classList.remove("hidden");
  body.textContent = "载入中…";
  try {
    const d = await api.post("/api/poem", { ref });
    if (d.error) { body.textContent = errText(d.error); return; }
    const p = d.poem;
    const blocks = [
      el("h2", {}, `《${esc(p.title)}》`),
      el("div", { class: "kv" }, `${esc(p.author)} · ${esc(p.dynasty)} · ${esc(p.book)}` +
        (p.cipai ? ` · 词牌「${esc(p.cipai)}」` : "") + ` · ${esc(p.poem_id)}`),
      el("div", {},
        el("span", { class: "layer A" }, "A 原文"),
        vpoem(p.lines)),
      el("div", { class: "card" },
        el("span", { class: "layer B" }, "B 计量"),
        el("div", { class: "kv" },
          `体裁：${esc(d.metrics.genre)}（${esc(d.metrics.genre_source)}）`, el("br"),
          `句式：${esc(d.metrics.char_pattern)}｜韵脚位置字：${(d.metrics.rhyme_feet || []).join("、") || "—"}`)),
      d.imagery && d.imagery.length ? el("div", { class: "card" },
        el("div", { class: "kv" }, "意象："),
        d.imagery.map((i) => el("span", { class: "tag", onclick: () => { go("imagery"); setTimeout(() => runImagery(i), 60); } }, i)),
        el("div", { class: "kv" }, "情感标记：" + (d.emotions || []).join("、"),
          el("br"), "题材：" + ((d.themes || []).join("、") || "未判定"))) : null,
      d.notes && d.notes.length ? el("div", { class: "card" },
        el("span", { class: "layer C" }, "C 注释"),
        d.notes.slice(0, 10).map((n) => el("div", { class: "kv" }, "· " + esc(n.text)))) : null,
      d.appreciation ? el("div", { class: "card" },
        el("span", { class: "layer C" }, "C 白话导读"),
        el("div", { class: "kv" }, esc(d.appreciation.text))) : null,
      d.author_bio ? el("div", { class: "card" },
        el("span", { class: "layer C" }, "C 作者小传"),
        el("div", { class: "kv" }, esc(d.author_bio.text))) : null,
      d.external_analysis ? el("div", { class: "card" },
        el("span", { class: "layer D" }, "D 外部分析"),
        el("div", { class: "kv" },
          `题材：${esc(d.external_analysis.subject)}｜主题：${esc(d.external_analysis.theme)}`, el("br"),
          `情感：${esc(d.external_analysis.emotion)}`, el("br"),
          el("i", {}, `（${esc(d.external_analysis.dataset)}，${esc(d.external_analysis.note)}）`))) : null,
      d.intertext && d.intertext.length ? el("div", { class: "card" },
        el("div", { class: "kv" }, "互文："),
        d.intertext.map((r) => el("div", { class: "kv" }, `${r.mode}「${r.shared_span}」↔ `,
          el("span", { class: "pid", onclick: () => openPoem(r.other) }, r.other)))) : null,
      el("button", { class: "mini", onclick: async () => {
        const g = await api.post("/api/gloss", { poem_ref: p.poem_id });
        if (g.glosses) {
          $("#drawer-body").append(el("div", { class: "card" },
            el("span", { class: "layer C" }, "C 训诂（高频字）"),
            g.glosses.map((x) => el("div", { class: "kv" },
              `「${x.char}」${x.shuowen ? esc(x.shuowen.gloss) : "字书无载"}`))));
        }
      } }, "查此诗高频字训诂"),
    ];
    body.replaceChildren(...blocks.filter(Boolean));
  } catch (e) { body.textContent = "错误：" + e.message; }
}
$("#drawer-close").addEventListener("click", () => $("#drawer").classList.add("hidden"));

/* ── 通用渲染 ───────────────────────────────────────────────────── */
function hitCard(h) {
  return el("div", { class: "hit" },
    el("div", { class: "t" }, `《${esc(h.title)}》`,
      el("span", { class: "dim" }, `　${esc(h.author)} · ${esc(h.dynasty)}${h.genre ? " · " + esc(h.genre) : ""}`)),
    h.quote ? el("div", { class: "quote" }, "「" + esc(h.quote) + "」") : null,
    el("div", { class: "meta" },
      el("span", { class: "pid", onclick: () => openPoem(h.poem_id) }, h.poem_id),
      h.score != null ? `　score ${h.score}` : "",
      h.matched_imagery && h.matched_imagery.length ? `　命中意象：${h.matched_imagery.join("、")}` : "",
      h.matched_themes && h.matched_themes.length ? `　命中题材：${h.matched_themes.join("、")}` : ""));
}

function answerBlock(text) {
  const div = el("div", { class: "answer" });
  div.append(linkifyIds(esc(text)));
  return div;
}

/* ── 视图 ───────────────────────────────────────────────────────── */
const views = {};

views.dashboard = async (main) => {
  main.replaceChildren(el("h2", {}, "总览"), el("div", { class: "card" }, "载入中…"));
  const s = await api.get("/api/stats");
  const srcRows = Object.entries(s.sources || {}).map(([k, v]) =>
    el("tr", {}, el("td", {}, k), el("td", {}, String(v.kept)), el("td", {}, String(v.raw))));
  const formRows = Object.entries(s.form_distribution || {}).sort((a, b) => b[1] - a[1]).slice(0, 12)
    .map(([k, v]) => el("span", { class: "tag" }, `${k} ${v}`));
  main.replaceChildren(
    el("h2", {}, "总览"),
    el("div", { class: "card hero" },
      el("div", { class: "hero-motto kai" }, "无原文，不成论断"),
      el("div", { class: "kv" },
        "把古典诗词语料转化为可回源、可推理、可比较、可教学、可研究、可调用的规则系统")),
    el("div", { class: "grid2" },
      el("div", { class: "card" }, el("h3", {}, "规则库"),
        el("div", { class: "kv" },
          `作品 ${s.poems} 首｜通过规则 ${(s.rules || {}).accepted} 条（拒绝 ${(s.rules || {}).rejected}）`, el("br"),
          `意象档案 ${s.imagery_profiles}｜题材 ${s.theme_profiles}｜词牌 ${s.cipai_profiles}｜诗人 ${s.author_profiles}`, el("br"),
          `韵组 ${s.rhyme_groups}｜互文 ${s.intertext_rules}｜D层绑定 ${s.external_analysis_linked}`)),
      el("div", { class: "card" }, el("h3", {}, "体裁分布"), formRows)),
    el("div", { class: "card" }, el("h3", {}, "语料来源（保留/原始）"),
      el("table", {}, el("tr", {}, el("th", {}, "来源"), el("th", {}, "保留"), el("th", {}, "原始")), srcRows)));
};

views.agent = async (main) => {
  const input = el("input", { placeholder: "如：明月在古诗里代表什么？/《春晓》的格律", style: "flex:1" });
  const role = el("select", {}, el("option", { value: "" }, "自动角色"),
    el("option", { value: "reader" }, "读者"), el("option", { value: "student" }, "学生"),
    el("option", { value: "researcher" }, "研究者"));
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "智能体思考取证中…"));
    try {
      const d = await api.post("/api/ask", { question: input.value, role: role.value });
      out.replaceChildren(
        el("div", { class: "card" }, answerBlock(d.answer)),
        el("div", { class: "card" }, el("h3", {}, "工具轨迹"),
          el("pre", {}, JSON.stringify(d.tool_trace, null, 1)),
          el("div", { class: "kv" }, `引用核验：${d.citation_report.ok ? "✓ 通过" : "✗ 有违规"}｜后端 ${d.backend}｜角色 ${d._role_label}`)));
    } catch (e) { out.replaceChildren(el("div", { class: "card err" }, e.message)); }
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "智能体（单体 ReAct + 引用核验）"),
    el("div", { class: "row" }, input, role, el("button", { class: "go", onclick: run }, "提问")), out);
};

views.council = async (main) => {
  const input = el("input", { placeholder: "如：对比《静夜思》和《月下独酌》的异同", style: "flex:1" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "合议庭审议中…"));
    try {
      const d = await api.post("/api/council", { question: input.value });
      const steps = (d.timeline || []).map((m) =>
        el("div", { class: "step" },
          el("div", { class: "who" }, `${m.role_cn}（${m.agent}）· ${m.action}`),
          el("div", { class: "what" }, linkifyIds(esc(m.content).slice(0, 800))),
          m.evidence_ids && m.evidence_ids.length ?
            el("div", { class: "dim" }, `证据 ${m.evidence_ids.length} 处`) : null));
      out.replaceChildren(
        el("div", { class: "card" },
          el("div", { class: "kv" }, `裁决：${d.decision}｜置信 ${d.confidence}｜后端 ${d.backend}`),
          answerBlock(d.answer)),
        el("div", { class: "card" }, el("h3", {}, "合议时间线"), el("div", { class: "tl" }, steps)));
    } catch (e) { out.replaceChildren(el("div", { class: "card err" }, e.message)); }
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "多智能体合议（规划→取证→专家→批评→裁决→综合）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "合议")), out);
};


views.scene = async (main) => {
  const input = el("input", { placeholder: "《静夜思》 / 《无题》@李商隐", style: "flex:1" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "构建诗境…"));
    const d = await api.post("/api/scene", { ref: input.value });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const maxAbs = Math.max(1, ...d.emotion_marker_density.map((v) => Math.abs(v)));
    show(out,
      el("div", { class: "card" },
        el("h3", {}, `《${esc(d.poem.title)}》`, el("span", { class: "dim" }, `　${esc(d.poem.author)} · ${esc(d.poem.dynasty)} · ${esc(d.poem.genre)}`),
          el("span", { class: "pid", onclick: () => openPoem(d.poem.poem_id) }, " " + d.poem.poem_id)),
        ...d.lines.map((l, i) => el("div", { class: "hit" },
          el("div", { class: "t kai", style: "font-size:18px" }, l.line),
          el("div", { class: "meta" },
            el("span", { class: "layer B" }, l.tone_pattern || "—"),
            l.imagery.length ? "　意象：" + l.imagery.join("、") : "",
            l.emotions.length ? "　情感：" + l.emotions.join("、") : "",
            l.negated.length ? "　（否定：" + l.negated.join("、") + "）" : ""),
          l.allusions.length ? el("div", { class: "kv" },
            "📜 疑似用典（候选，待语境确认）：" + l.allusions.map((a) =>
              `${a.allusion}〔典源候选：${a.source}｜常用义：${a.implies}` +
              (a.ambiguity_note ? `｜⚠ ${a.ambiguity_note}` : "") + "〕").join("；")) : null,
          el("div", { class: "bar " + (d.emotion_marker_density[i] >= 0 ? "pos" : "neg"),
            style: `width:${Math.abs(d.emotion_marker_density[i]) / maxAbs * 60 + 2}%` })))),
      d.couplets && d.couplets.length ? el("div", { class: "card" }, el("h3", {}, "对仗（B层启发式）"),
        d.couplets.map((c) => el("div", { class: "kv" },
          `${c.couplet}：${c.verdict}｜平仄相对率 ${c.tone_opposition_rate}｜范畴对位率 ${c.category_match_rate ?? "—"}`))) : null,
      el("div", { class: "card dim" }, esc(d.note)));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "进入一首诗（逐句：意象/情感标记/平仄/典故候选 + 情感标记密度）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "进入")), out);
};

views.search = async (main) => {
  const input = el("input", { placeholder: "诗句/意象/《题名》/作者…", style: "flex:1" });
  const dyn = el("select", {}, ["", "先秦", "汉魏", "唐", "五代", "宋", "元", "清"].map((d) =>
    el("option", { value: d }, d || "全部朝代")));
  const expand = el("select", {}, el("option", { value: "" }, "不扩展"),
    el("option", { value: "1" }, "意象扩展"));
  const out = el("div", { class: "card" });
  const run = async () => {
    out.textContent = "检索中…";
    const d = await api.post("/api/search", { query: input.value, top_k: 10, dynasty: dyn.value, expand: !!expand.value });
    out.replaceChildren(...(d.hits || []).map(hitCard));
    if (!(d.hits || []).length) out.textContent = "无命中";
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "原文检索（BM25 + 结构化过滤 + 意象覆盖重排）"),
    el("div", { class: "row" }, input, dyn, expand, el("button", { class: "go", onclick: run }, "检索")), out);
};

views.match = async (main) => {
  const input = el("input", { placeholder: "心境/场景：想家 / 送别朋友 / 秋夜失眠…", style: "flex:1" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "匹配中…"));
    const d = await api.post("/api/match", { mood: input.value, top_k: 8 });
    out.replaceChildren(
      el("div", { class: "card" }, el("div", { class: "kv" },
        `解析：意象 ${(d.query.imagery || []).join("、") || "—"}｜题材 ${(d.query.themes || []).join("、") || "—"}｜情感 ${(d.query.emotions || []).join("、") || "—"}`)),
      el("div", { class: "card" }, ...(d.recommendations || []).map(hitCard)));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "情境荐诗（心境 → 意象/题材/情感 → 证据计分）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "荐诗")), out);
};

views.differential = async (main) => {
  const a = el("input", { placeholder: "《静夜思》" }), b = el("input", { placeholder: "《月下独酌》" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "对比中…"));
    const d = await api.post("/api/differential", { refs: [a.value, b.value].filter(Boolean) });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    out.replaceChildren(
      el("div", { class: "card" },
        (d.poems || []).map((p) => el("div", { class: "hit" },
          el("div", { class: "t" }, `《${esc(p.title)}》`, el("span", { class: "dim" }, `　${esc(p.author)}`)),
          el("div", { class: "quote" }, (p.lines || []).slice(0, 2).join("，")),
          el("span", { class: "pid", onclick: () => openPoem(p.poem_id) }, p.poem_id)))),
      el("div", { class: "card" }, el("table", {},
        el("tr", {}, el("th", {}, "对比轴"), el("th", {}, "内容")),
        (d.contrast || []).map((r) => el("tr", {}, el("td", {}, r.axis), el("td", {}, r.detail))))));
  };
  main.replaceChildren(el("h2", {}, "对比鉴赏（体裁/意象/题材/情感/互文逐轴）"),
    el("div", { class: "row" }, a, b, el("button", { class: "go", onclick: run }, "对比")), out);
};

views.teach = async (main) => {
  const input = el("input", { placeholder: "题材（思乡羁旅）/体裁（七绝）/意象（月）/诗人（李白）" });
  const out = el("div", {});
  const run = async (topic) => {
    out.replaceChildren(el("div", { class: "card" }, "备课中…"));
    const d = await api.post("/api/teach", { topic: topic || input.value });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const les = d.lesson;
    out.replaceChildren(el("div", { class: "card" },
      el("h3", {}, `【${esc(les.type)}】${esc(les.topic)}`),
      el("div", { class: "answer" }, esc(les.outline)),
      les.bio ? el("div", { class: "kv" }, el("span", { class: "layer C" }, "C 小传"), esc(les.bio)) : null,
      les.markers ? el("div", { class: "kv" }, "标记词：" + les.markers.join("、")) : null,
      el("h3", {}, "代表作"),
      (les.representative || []).map((r) => el("div", { class: "hit" },
        el("div", { class: "t" }, `《${esc(r.title || r.topic || "")}》`,
          el("span", { class: "dim" }, r.author ? `　${esc(r.author)}` : "")),
        r.quote ? el("div", { class: "quote" }, "「" + esc(r.quote) + "」") : null,
        el("span", { class: "pid", onclick: () => openPoem(r.poem_id) }, r.poem_id))),
      les.exercise ? el("div", { class: "kv", style: "margin-top:8px" }, "📝 " + esc(les.exercise)) : null));
  };
  const quick = ["思乡羁旅", "送别怀人", "边塞征戍", "七绝", "五律", "词", "月", "柳", "李白", "杜甫", "苏轼"]
    .map((t) => el("span", { class: "tag", onclick: () => { input.value = t; run(t); } }, t));
  main.replaceChildren(el("h2", {}, "教学"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: () => run() }, "开讲")),
    el("div", { class: "card" }, "快捷主题：", quick), out);
};

let runImagery = () => {};
views.imagery = async (main) => {
  const input = el("input", { placeholder: "月 / 柳 / 雁 / 夕阳…" });
  const out = el("div", {});
  const run = async (name) => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/imagery", { imagery: name || input.value });
    if (d.error) {
      out.replaceChildren(el("div", { class: "card" }, el("div", { class: "err" }, errText(d.error)),
        (d.available || []).map((i) => el("span", { class: "tag", onclick: () => { input.value = i; run(i); } }, i))));
      return;
    }
    const r = d.imagery_profile;
    out.replaceChildren(el("div", { class: "card" },
      el("h3", {}, `意象「${esc(r.imagery)}」 · ${r.n_poems} 首支撑 · ${esc(r.release_level)}`),
      el("div", { class: "kv" }, "表面形式：" + (r.surface_forms || []).join("、")),
      el("h3", {}, "情感关联（语料归纳）"),
      el("table", {}, el("tr", {}, el("th", {}, "情感"), el("th", {}, "支撑"), el("th", {}, "例证")),
        (r.emotion_associations || []).map((a) => el("tr", {},
          el("td", {}, a.emotion), el("td", {}, String(a.support)),
          el("td", {}, `《${esc(a.example.title)}》「${esc(a.example.quote)}」`,
            el("span", { class: "pid", onclick: () => openPoem(a.example.poem_id) }, " " + a.example.poem_id))))),
      (r.conflicts || []).map((c) => el("div", { class: "kv warn" }, `⚖ ${c.emotions.join(" vs ")}：${c.note}`)),
      el("h3", {}, "共现意象"),
      (r.co_imagery || []).map((c) => el("span", { class: "tag", onclick: () => { input.value = c.imagery; run(c.imagery); } }, `${c.imagery} ${c.count}`)),
      el("div", { style: "margin-top:10px" },
        el("button", { class: "mini", onclick: async (ev) => {
          ev.target.textContent = "载入中…";
          const d2 = await api.post("/api/imagery", { imagery: r.imagery, all_examples: true });
          const ae = d2.all_examples || {};
          ev.target.replaceWith(el("div", { class: "card" },
            el("h3", {}, `全部例证（列出 ${ae.n_listed}／总支撑 ${ae.n_total} 首，点击回源）`),
            el("div", { class: "dim" }, esc(ae.note)),
            (ae.examples || []).map((x) => el("div", { class: "hit" },
              el("div", { class: "t" }, `《${esc(x.title)}》`,
                el("span", { class: "dim" }, `　${esc(x.author)} · ${esc(x.dynasty)}`)),
              x.quote ? el("div", { class: "quote" }, "「" + esc(x.quote) + "」") : null,
              el("span", { class: "pid", onclick: () => openPoem(x.poem_id) }, x.poem_id)))));
        } }, "浏览全部例证作品"))));
  };
  runImagery = run;
  main.replaceChildren(el("h2", {}, "意象档案（跨诗归纳 + 证据链）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: () => run() }, "查询")), out);
};

views.cipai = async (main) => {
  const input = el("input", { placeholder: "浣溪沙 / 忆江南 / 水调歌头…（支持同调异名）" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/cipai", { cipai: input.value });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const r = d.cipai_profile, pu = d.cipu;
    const poems = d.all_poems || [];
    const LIMIT = 24;
    const poemHit = (p) => el("div", { class: "hit" },
      el("div", { class: "t" }, `《${esc(p.title)}》`,
        el("span", { class: "dim" }, `　${esc(p.author)} · ${esc(p.dynasty)}`)),
      el("span", { class: "pid", onclick: () => openPoem(p.poem_id) }, p.poem_id));
    const list = el("div", {}, poems.slice(0, LIMIT).map(poemHit));
    show(out,
      d.resolved_via ? el("div", { class: "card dim" }, "✦ " + esc(d.resolved_via)) : null,
      pu ? el("div", { class: "card" },
        el("h3", {}, `词谱「${esc(pu.cipai)}」`,
          el("span", { class: "dim" },
            `　${esc(pu.category)}` +
            ((pu.aliases || []).length ? `　又名：${pu.aliases.join("、")}` : ""))),
        pu.intro ? el("div", { class: "kv" }, esc(pu.intro)) : null,
        (pu.forms || []).map((f) => el("div", {},
          el("h3", {}, f.label),
          el("div", { class: "pu" }, f.pattern.split("\n").map((ln) => el("div", {}, ln))))),
        el("div", { class: "dim" }, `${esc(pu.legend)}　—— ${esc(pu.source)}`)) : null,
      r ? el("div", { class: "card" },
        el("h3", {}, `语料归纳定格「${esc(r.cipai)}」（${r.n_poems} 首）`),
        el("div", { class: "kv" },
          `众数句式：${esc(r.char_pattern)}`, el("br"),
          `一致率：${Math.round(r.pattern_consistency * 100)}%｜众数句数：${r.line_count_mode}`, el("br"),
          el("i", {}, esc(r.note)))) : null,
      poems.length ? el("div", { class: "card" },
        el("h3", {}, `全部例词（${poems.length} 首，点击回源）`),
        list,
        poems.length > LIMIT ? el("button", { class: "mini", onclick: (ev) => {
          list.append(...poems.slice(LIMIT).map(poemHit));
          ev.target.remove();
        } }, `展开其余 ${poems.length - LIMIT} 首`) : null) : null,
      el("div", { class: "card dim" }, esc(d.note)));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "词牌定格（龙榆生词谱权威层 + 语料归纳，双层互证）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "查询")), out);
};

views.author = async (main) => {
  const input = el("input", { placeholder: "支持字号别名：苏东坡 / 稼轩 / 容若 / 易安居士…" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/author", { author: input.value });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const r = d.author_profile;
    show(out,
      d.resolved_via ? el("div", { class: "card dim" }, "✦ " + esc(d.resolved_via)) : null,
      el("div", { class: "card" },
      el("h3", {}, `${esc(r.author)}（${esc(r.dynasty)}）· 语料 ${r.n_poems} 首`),
      el("div", { class: "kv" },
        "高频意象：", (r.top_imagery || []).map((x) => el("span", { class: "tag" }, `${x.imagery} ${x.count}`)),
        el("br"), "高频题材：", (r.top_themes || []).map((x) => el("span", { class: "tag" }, `${x.theme} ${x.count}`)),
        el("br"), "体裁分布：" + Object.entries(r.form_distribution || {}).sort((a, b) => b[1] - a[1]).slice(0, 6)
          .map(([k, v]) => `${k} ${v}`).join("｜")),
      r.bio ? el("div", { class: "card" }, el("span", { class: "layer C" }, "C 小传"),
        el("div", { class: "kv" }, esc(r.bio))) : null,
      el("h3", {}, "代表作"),
      (r.representative_poems || []).map((p) => el("div", { class: "hit" },
        el("div", { class: "t" }, `《${esc(p.title)}》`),
        el("span", { class: "pid", onclick: () => openPoem(p.poem_id) }, p.poem_id)))));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "诗人档案（支持字/号/别称查询）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "查询")), out);
};

views.gloss = async (main) => {
  const input = el("input", { placeholder: "1-8 个汉字，如：雎鸠 / 婵娟；或《题名》查高频字" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查阅字书…"));
    const v = input.value.trim();
    const body = v.startsWith("《") ? { poem_ref: v } : { chars: v };
    const d = await api.post("/api/gloss", body);
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    out.replaceChildren(el("div", { class: "card" },
      el("div", { class: "kv" }, el("span", { class: "layer C" }, "C 训诂"), el("i", {}, esc(d.note))),
      el("table", {}, el("tr", {}, el("th", {}, "字"), el("th", {}, "说文解字"), el("th", {}, "尔雅")),
        (d.glosses || []).map((g) => el("tr", {},
          el("td", { style: "font-size:18px" }, g.char),
          el("td", {}, g.shuowen ?
            `${esc(g.shuowen.gloss)}（${esc(g.shuowen.radical)}，${esc(g.shuowen.fanqie)}）` :
            el("span", { class: "dim" }, "无载")),
          el("td", {}, (g.erya || []).length ?
            g.erya.map((e2) => el("div", {}, `${e2.members.slice(0, 8).join("、")}，${e2.gloss}`)) :
            el("span", { class: "dim" }, "—"))))),
      el("div", { class: "dim" }, "来源：" + esc(d.source))));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "字义训诂（说文解字 9,829 条 + 尔雅 19 篇，C层旁证）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "查字")), out);
};

views.compose = async (main) => {
  const genre = el("select", {}, ["七绝", "五绝", "七律", "五律", "词牌…"].map((g) => el("option", { value: g }, g)));
  const cipaiInput = el("input", { placeholder: "词牌名，如：忆江南", style: "min-width:160px;display:none" });
  genre.addEventListener("change", () => {
    cipaiInput.style.display = genre.value === "词牌…" ? "" : "none";
  });
  const rhyme = el("input", { placeholder: "韵脚字（可选），如：秋", maxlength: "1", style: "min-width:160px" });
  const mood = el("input", { placeholder: "立意/心境（可选），如：送别友人", style: "flex:1" });
  const avoid = el("input", { placeholder: "回避意象（顿号分隔）", style: "min-width:160px" });
  const chosen = new Set();
  const imageryBar = el("div", { class: "kv" }, "选用意象（点选）：");
  ["月", "柳", "雁", "花", "酒", "舟", "山", "云", "雨", "灯", "松", "剑", "马", "梅"].forEach((c) => {
    const tag = el("span", { class: "tag", onclick: () => {
      if (chosen.has(c)) { chosen.delete(c); tag.style.color = ""; tag.style.borderColor = ""; }
      else { chosen.add(c); tag.style.color = "var(--zhu)"; tag.style.borderColor = "var(--zhu-soft)"; }
    } }, c);
    imageryBar.append(tag);
  });
  const out = el("div", {});
  const runHelper = async () => {
    out.replaceChildren(el("div", { class: "card" }, "备料中…"));
    try {
      if (genre.value === "词牌…") {
        const d = await api.post("/api/compose", { cipai: cipaiInput.value });
        if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
        const pu = d.cipu;
        show(out,
          el("div", { class: "card dim" }, esc(d.declaration)),
          d.resolved_via ? el("div", { class: "card dim" }, "✦ " + esc(d.resolved_via)) : null,
          pu ? el("div", { class: "card" },
            el("h3", {}, `词谱「${esc(pu.cipai)}」`,
              el("span", { class: "dim" }, `　${esc(pu.category)}` +
                ((pu.aliases || []).length ? `　又名：${pu.aliases.join("、")}` : ""))),
            pu.intro ? el("div", { class: "kv" }, esc(pu.intro)) : null,
            (pu.forms || []).map((f) => el("div", {},
              el("h3", {}, f.label),
              el("div", { class: "pu" }, f.pattern.split("\n").map((ln) => el("div", {}, ln))))),
            el("div", { class: "dim" }, `${esc(pu.legend)}　—— ${esc(pu.source)}`)) :
            el("div", { class: "card warn" }, "词谱层无此调（可参考语料归纳定格）"),
          d.cipai_profile ? el("div", { class: "card" },
            el("h3", {}, `语料归纳（${d.cipai_profile.n_poems} 首）`),
            el("div", { class: "kv" }, `众数句式：${esc(d.cipai_profile.char_pattern)}`)) : null,
          (d.example_poems || []).length ? el("div", { class: "card" },
            el("h3", {}, `例词（${d.n_examples_total} 首中的前 ${d.example_poems.length}，全部见「词牌定格」视图）`),
            d.example_poems.map((p) => el("div", { class: "hit" },
              el("div", { class: "t" }, `《${esc(p.title)}》`, el("span", { class: "dim" }, `　${esc(p.author)}`)),
              el("span", { class: "pid", onclick: () => openPoem(p.poem_id) }, p.poem_id)))) : null,
          el("div", { class: "card dim" }, esc(d.note)));
        return;
      }
      const d = await api.post("/api/compose", {
        genre: genre.value, rhyme_char: rhyme.value, mood: mood.value,
        imagery: [...chosen],
        avoid_imagery: avoid.value.split(/[、,，\s]+/).filter(Boolean) });
      show(out,
        el("div", { class: "card dim" }, esc(d.declaration)),
        el("div", { class: "card" },
          el("h3", {}, `${esc(d.genre)} 标准谱（○平 ●仄 ◎常规可宽）`),
          el("div", { class: "grid2" },
            Object.entries(d.templates || {}).map(([q, lines]) => el("div", {},
              el("div", { class: "kv" }, el("b", {}, q)),
              el("div", { class: "pu" }, lines.map((l) => el("div", {}, l)))))),
          el("div", { class: "dim" }, esc(d.template_note))),
        d.rhyme ? el("div", { class: "card" },
          el("h3", {}, `韵部「${esc(d.rhyme.char)}」`),
          el("div", { class: "kv" },
            `平水韵：${(d.rhyme.pingshui || []).join("、") || "—"}｜词林正韵：${(d.rhyme.cilin || []).join("、") || "—"}`),
          el("div", {}, (d.rhyme.candidates || []).map((c) => el("span", { class: "tag kai" }, c))),
          el("div", { class: "dim" }, esc(d.rhyme.note))) : null,
        (d.chosen_imagery || []).length ? el("div", { class: "card" },
          el("h3", {}, "选用意象（语料档案参照）"),
          d.chosen_imagery.map((c) => el("div", { class: "hit" },
            el("span", { class: "tag" }, c.imagery),
            el("span", { class: "kv" }, (c.associations || []).length ?
              `　多与「${c.associations.join("、")}」相系` : "　" + esc(c.note || "")),
            (c.co_imagery || []).length ? el("span", { class: "dim" },
              `　常共现：${c.co_imagery.join("、")}`) : null,
            c.example && c.example.quote ? el("div", { class: "quote" },
              `「${esc(c.example.quote)}」`,
              c.example.poem_id ? el("span", { class: "pid",
                onclick: () => openPoem(c.example.poem_id) }, " " + c.example.poem_id) : null) : null))) : null,
        d.imagery_suggestions && d.imagery_suggestions.length ? el("div", { class: "card" },
          el("h3", {}, "意象建议（语料档案，可回避）"),
          d.imagery_suggestions.map((s) => el("div", { class: "hit" },
            el("span", { class: "tag", onclick: () => { go("imagery"); setTimeout(() => runImagery(s.imagery), 60); } }, s.imagery),
            el("span", { class: "kv" }, s.association ? `　多与「${s.association}」相系` : ""),
            s.example && s.example.quote ? el("div", { class: "quote" }, `「${esc(s.example.quote)}」`,
              s.example.poem_id ? el("span", { class: "pid", onclick: () => openPoem(s.example.poem_id) }, " " + s.example.poem_id) : null) : null))) : null);
    } catch (e) { out.replaceChildren(el("div", { class: "card err" }, e.message)); }
  };
  const draft = el("textarea", { placeholder: "草稿逐句一行，如：\n白日依山尽\n黄河入海流\n欲穷千里目\n更上一层楼" });
  const outc = el("div", {});
  const runCheck = async () => {
    outc.replaceChildren(el("div", { class: "card" }, "复核中…"));
    try {
      const d = await api.post("/api/check_draft", { lines: draft.value.split(/\n+/), genre: genre.value });
      if (d.error) { outc.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
      const t = d.tonal || {}, tm = t.template_match || {};
      show(outc,
        el("div", { class: "card" },
          el("span", { class: "layer B" }, "B 计量"),
          el("div", { class: "pu" }, (t.line_patterns || []).map((p) => el("div", {}, p))),
          el("div", { class: "kv" },
            tm.best_fit ? `最近标准谱：${tm.best_fit}（严格位偏差 ${tm.deviations}）` : "未匹配标准谱（非 4/8 句齐言近体）",
            el("br"),
            `首句入韵：${t.first_line_rhymes === true ? "是" : t.first_line_rhymes === false ? "否" : "不可判"}` +
            `｜两读字：${t.uncertain_chars ?? 0} 处｜韵调：${esc(t.rhyme_tone || "—")}`),
          (t.issues || []).length ? el("div", { class: "kv warn" },
            "律则提示：" + t.issues.map((i) => typeof i === "string" ? i : (i.issue || i.type || JSON.stringify(i))).join("；")) : null,
          (t.rhyme_feet_phonology || []).length ? el("table", {},
            el("tr", {}, el("th", {}, "韵脚"), el("th", {}, "声调"), el("th", {}, "平水韵"), el("th", {}, "词林正韵")),
            t.rhyme_feet_phonology.map((f) => el("tr", {},
              el("td", { class: "kai" }, f.char), el("td", {}, (f.tones || []).join("/")),
              el("td", {}, (f.pingshui || []).join("/")), el("td", {}, (f.cilin || []).join("/"))))) : null,
          el("div", { class: "dim" }, esc(t.note))),
        d.collisions && d.collisions.length ? el("div", { class: "card" },
          el("h3", {}, "撞句提醒"),
          d.collisions.map((c) => el("div", { class: "kv" }, `「${esc(c.line)}」重合「${esc(c.overlaps)}」　`,
            (c.with || []).map((w) => el("span", { class: "pid", onclick: () => openPoem(w) }, w + " "))))) : null,
        el("div", { class: "card dim" }, esc(d.note)));
    } catch (e) { outc.replaceChildren(el("div", { class: "card err" }, e.message)); }
  };
  main.replaceChildren(
    el("h2", {}, "创作实验室（今人拟作辅助，永不伪托古人）"),
    el("div", { class: "card" },
      el("h3", {}, "备料：标准谱／词谱 · 韵部候选 · 意象选用"),
      el("div", { class: "row" }, genre, cipaiInput, rhyme, mood, avoid,
        el("button", { class: "go", onclick: runHelper }, "备料")),
      imageryBar,
      out),
    el("div", { class: "card" },
      el("h3", {}, "草稿复核：平仄 / 律则 / 撞句"),
      draft,
      el("div", { class: "row", style: "margin-top:8px" },
        el("button", { class: "go", onclick: runCheck }, "复核")),
      outc));
};

views.gufeng = async (main) => {
  const theme = el("input", { placeholder: "主题/立意，如：戍边思归 / 宫怨", style: "flex:1" });
  const rhyme = el("input", { placeholder: "首解韵脚字（可选）", maxlength: "1", style: "min-width:150px" });
  const nlines = el("select", {}, ["12", "16", "24", "32", "40"].map((n) =>
    el("option", { value: n }, n + " 句")));
  const reqs = el("input", { placeholder: "其他要求（可选），如：以秋雁开篇、结句望乡", style: "flex:1" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "检索规则、组合方案中…"));
    try {
      const d = await api.post("/api/compose_gufeng", {
        theme: theme.value, rhyme_char: rhyme.value,
        n_lines: parseInt(nlines.value, 10), requirements: reqs.value });
      const plan = d.plan || {};
      show(out,
        el("div", { class: "card dim" }, esc(d.declaration)),
        el("div", { class: "card" },
          el("h3", {}, "创作方案（检索组合，B层）"),
          el("div", { class: "kv" }, `体式：${esc(plan.genre)}｜${plan.n_lines} 句 · ${plan.segments} 解`),
          el("table", {},
            el("tr", {}, el("th", {}, "解"), el("th", {}, "句序"), el("th", {}, "韵组"), el("th", {}, "候选韵脚")),
            (plan.rhyme_plan || []).map((r) => el("tr", {},
              el("td", {}, String(r.segment)), el("td", {}, r.lines),
              el("td", {}, r.group), el("td", { class: "kai" }, (r.candidates || []).join(" "))))),
          (plan.imagery_suggestions || []).length ? el("div", { class: "kv" },
            "意象建议：", plan.imagery_suggestions.map((i) => el("span", { class: "tag" }, i))) : null,
          el("div", { class: "kv" }, (plan.conventions || []).map((c) => el("div", {}, "· " + c)))),
        el("div", { class: "card" },
          el("h3", {}, "语料范例（歌行体，逐字回源）"),
          (plan.references || []).map((rf) => el("div", { class: "hit" },
            el("div", { class: "t" }, `《${esc(rf.title)}》`,
              el("span", { class: "dim" }, `　${esc(rf.author)} · ${rf.n_lines} 句`),
              el("span", { class: "pid", onclick: () => openPoem(rf.poem_id) }, " " + rf.poem_id)),
            el("div", { class: "quote" }, (rf.excerpt || []).join("，") + "……")))),
        d.poem && d.poem.length ? el("div", { class: "card" },
          el("h3", {}, "AI 代拟稿（今人拟作）"),
          el("div", { class: "poemlines" }, d.poem.map((ln) => el("div", {}, ln))),
          el("div", { class: d.verification && d.verification.passed ? "kv ok" : "kv warn" },
            d.verification ? (d.verification.passed ? "✓ 形式核验通过" :
              "⚠ 形式核验未全过：" + (d.verification.issues || []).join("；")) : ""),
          el("div", { class: "dim" }, d.verification ? esc(d.verification.note) : "")) :
          el("div", { class: "card warn" }, esc(d.note || "")),
        el("div", { class: "card dim" }, `后端：${esc(d.backend)}`));
    } catch (e) { out.replaceChildren(el("div", { class: "card err" }, e.message)); }
  };
  main.replaceChildren(
    el("h2", {}, "古风长篇（歌行体 · AI 智能体创作，参照长恨歌等语料范例）"),
    el("div", { class: "row" }, theme, rhyme, nlines),
    el("div", { class: "row" }, reqs, el("button", { class: "go", onclick: run }, "起稿")),
    out);
};

views.feihua = async (main) => {
  const charInput = el("input", { placeholder: "令字（单字），如：花 / 月 / 春", maxlength: "1", style: "min-width:180px" });
  const lineInput = el("input", { placeholder: "你的应对句（语料原句，简繁不限）", style: "flex:1", disabled: true });
  const log = el("div", {});
  const state = { char: "", round: 0, used: [], over: false };
  const push = (who, node) => {
    log.prepend(el("div", { class: "hit" },
      el("div", { class: "kv" }, el("b", {}, who)), node));
  };
  const machineTurn = async (userLine) => {
    const d = await api.post("/api/feihua", {
      char: state.char, user_line: userLine || "",
      exclude_ids: state.used, round_no: state.round });
    if (d.error) { push("裁判", el("div", { class: "err" }, errText(d.error))); return; }
    if (userLine) {
      const c = d.user_check || {};
      if (c.valid) {
        state.used.push(c.poem_id);
        push("你", el("div", {},
          el("div", { class: "quote" }, userLine),
          el("div", { class: "kv ok" }, `✓ 语料实有：《${esc(c.title)}》${esc(c.author)} `,
            el("span", { class: "pid", onclick: () => openPoem(c.poem_id) }, c.poem_id))));
      } else {
        push("你", el("div", {},
          el("div", { class: "quote" }, userLine),
          el("div", { class: "kv err" }, `✗ ${esc(c.reason)}（此句不计，请再试）`)));
        return;
      }
    }
    if (d.reply) {
      state.used.push(d.reply.poem_id);
      state.round += 1;
      push("诗海", el("div", {},
        el("div", { class: "quote", style: "font-size:16px" }, d.reply.line),
        el("div", { class: "kv" }, `《${esc(d.reply.title)}》${esc(d.reply.author)} · ${esc(d.reply.dynasty)} `,
          el("span", { class: "pid", onclick: () => openPoem(d.reply.poem_id) }, d.reply.poem_id))));
    } else {
      state.over = true;
      lineInput.disabled = true;
      push("裁判", el("div", { class: "kv ok" }, "语料中含令字的未用句已尽——你赢了！🏆"));
    }
  };
  const start = async () => {
    const ch = (charInput.value || "").trim();
    if (!ch) return;
    state.char = ch; state.round = 0; state.used = []; state.over = false;
    log.replaceChildren();
    lineInput.disabled = false;
    push("裁判", el("div", { class: "kv" },
      `令字「${ch}」。规则（参照中国诗词大会）：轮流吟出含令字的语料原句，作品不重复；`
      + "接不上者负。诗海先行——"));
    await machineTurn("");
  };
  lineInput.addEventListener("keydown", async (ev) => {
    if (ev.key === "Enter" && !state.over && lineInput.value.trim()) {
      const v = lineInput.value.trim();
      lineInput.value = "";
      await machineTurn(v);
    }
  });
  charInput.addEventListener("keydown", (ev) => { if (ev.key === "Enter") start(); });
  main.replaceChildren(
    el("h2", {}, "飞花令（对句须语料实有，逐字回源判定）"),
    el("div", { class: "row" }, charInput,
      el("button", { class: "go", onclick: start }, "开局"), lineInput),
    el("div", { class: "card" }, log));
};

views.rhyme = async (main) => {
  const input = el("input", { placeholder: "单字，如：天 / 秋 / 愁", maxlength: "2" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/rhyme", { char: input.value });
    show(out, el("div", { class: "card" },
      el("div", { class: "kv" }, el("i", {}, esc(d.note))),
      ...(d.groups || []).map((g) => el("div", { class: "card" },
        el("h3", {}, `韵组【${esc(g.label)}】 · ${g.members.length} 字 · 支撑 ${g.n_poems} 首`),
        el("div", { class: "answer" }, (g.members || []).join(" ")),
        el("div", { class: "kv" }, "高频共现对：" + (g.edge_examples || []).slice(0, 6)
          .map((e2) => `${e2.pair.join("")}×${e2.co_occurrence}`).join("｜")),
        (g.verse_examples || []).length ? el("div", {},
          el("h3", {}, "实押例证（点击回源原诗）"),
          g.verse_examples.map((v) => el("div", { class: "hit" },
            el("div", { class: "t" }, `《${esc(v.title)}》`,
              el("span", { class: "dim" }, `　${esc(v.author)} · ${esc(v.dynasty)}`),
              el("span", { class: "pid", onclick: () => openPoem(v.poem_id) }, " " + v.poem_id)),
            el("div", { class: "quote" },
              (v.rhyming_lines || []).map((rl) => `${rl.line}（${rl.foot}）`).join("　"))))) : null)),
      (d.groups || []).length ? null : el("div", { class: "dim" }, "无该字的韵组记录")));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "韵伴聚类（近体诗偶数句尾字共现归纳）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "查询")), out);
};

views.intertext = async (main) => {
  const input = el("input", { placeholder: "《题名》或诗句片段", style: "flex:1" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "检测中…"));
    const v = input.value.trim();
    const body = v.startsWith("《") ? { poem_ref: v } : { text: v };
    const d = await api.post("/api/intertext", body);
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const pairs = (d.pairs || []).map((r) => el("div", { class: "hit" },
      el("div", { class: "t" }, `${r.mode}　`, el("span", { class: "quote" }, `「${esc(r.shared_span)}」`)),
      el("div", { class: "meta" },
        el("span", { class: "pid", onclick: () => openPoem(r.source_poem_id) }, r.source_poem_id), " ↔ ",
        el("span", { class: "pid", onclick: () => openPoem(r.target_poem_id) }, r.target_poem_id))));
    out.replaceChildren(el("div", { class: "card" },
      pairs.length ? pairs : el("div", { class: "dim" }, esc(d.note || "无逐字互文命中")),
      ...(d.nearest_poems || []).map(hitCard)));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "互文检测（重出互见/袭用/化用，5-gram 逐字对齐）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "检测")), out);
};

views.research = async (main) => {
  main.replaceChildren(el("h2", {}, "研究端"), el("div", { class: "card" }, "载入中…"));
  const d = await api.post("/api/research", {});
  if (d.error) { main.replaceChildren(el("h2", {}, "研究端"), el("div", { class: "card err" }, errText(d.error))); return; }
  const dynRows = Object.entries(d.dynasty_poem_counts || {}).map(([k, v]) => {
    const w = Math.min(100, v / 60);
    return el("div", { class: "kv" }, `${k}　${v}`,
      el("div", { class: "bar", style: `width:${w}%;height:6px;margin:2px 0 6px` }));
  });
  main.replaceChildren(
    el("h2", {}, "研究端（确定性统计资产）"),
    el("div", { class: "grid2" },
      el("div", { class: "card" }, el("h3", {}, "朝代分布"), dynRows),
      el("div", { class: "card" }, el("h3", {}, "意象共现 Top 边"),
        (d.imagery_network_top.edges || []).slice(0, 16).map((e2) =>
          el("div", { class: "kv" }, `${e2.source} — ${e2.target}　×${e2.weight}`)))),
    el("div", { class: "card" }, el("h3", {}, "情感 × 意象矩阵（Top）"),
      el("table", {}, el("tr", {}, el("th", {}, "情感"), el("th", {}, "高频意象")),
        Object.entries(d.emotion_imagery_matrix || {}).map(([emo, imgs]) =>
          el("tr", {}, el("td", {}, emo),
            el("td", {}, Object.entries(imgs).slice(0, 8).map(([i, c]) => `${i} ${c}`).join("｜")))))));
};

views.skills = async (main) => {
  main.replaceChildren(el("h2", {}, "Skill 库"), el("div", { class: "card" }, "载入中…"));
  const d = await api.get("/api/skills");
  main.replaceChildren(el("h2", {}, "Skill 库（编译产物，可被任意智能体运行时装载）"),
    el("div", { class: "card" },
      el("div", { class: "kv" }, `技能树：${esc(d.tree)}｜总数：${d.total_skills}`),
      el("table", {}, el("tr", {}, el("th", {}, "家族"), el("th", {}, "数量")),
        Object.entries(d.families || {}).map(([k, v]) =>
          el("tr", {}, el("td", {}, k), el("td", {}, String(v)))))),
    el("div", { class: "card kv" },
      "每个 Skill = SKILL.md（YAML frontmatter + 文档）+ rules.jsonl + examples.jsonl；",
      el("br"), "位于 data/skills/cnpoetry/，同时被本系统的 SkillRAG 路由与外部运行时使用。"));
};

views.about = async (main) => {
  main.replaceChildren(el("h2", {}, "关于"),
    el("div", { class: "card answer" },
      "诗海赫尔墨斯（Hermes-CNPoetry）\n" +
      "中华古典诗词自主规则挖掘与 Skill 生成系统 —— 把古典诗词语料转化为可回源、可推理、可比较、可教学、可研究、可调用的规则系统。\n\n" +
      "核心原则：无原文，不成论断。无篇目编号，不成证据。无证据链，不成回答。\n\n" +
      "· 证据分级：A 原文 / B 计量 / C 旁证 / D 外部分析 / E 模型解释\n" +
      "· 意象规则逐字回源，失败进入 rejected/；对抗性测试注入伪造证据并断言其被拒绝\n" +
      "· 纯 Python 标准库实现，零第三方依赖，离线可全功能运行\n" +
      "· 真实大模型接入：Azure OpenAI / Poe / MiniMax 原生直连（标准库 urllib），" +
      "或经 LiteLLM 接 Anthropic/OpenAI 等 100+ 供应商；智能体为模型自主选择工具的 " +
      "ReAct 循环，所有生成内容过引用核验与论断核验双闸门\n" +
      "· 词谱权威层：龙榆生《唐宋词格律》153 调（调名异名/定格变格），与语料归纳互证\n\n" +
      "数据源（三源实质纳入）：chinese-poetry（MIT，A层核心语料）；" +
      "PoetryMTEB（D层外部分析，3,084 首双向回源绑定）；" +
      "gujilab/chinese-classical-corpus（CC0，说文解字 9,829 条 + 尔雅训释 → C层训诂）；" +
      "OpenCC 字表（简繁归一）；龙榆生《唐宋词格律》（词谱权威层）。\n" +
      "架构参照：Shanghan-Hermes（伤寒-赫尔墨斯）。\n\n" +
      "研发机构：医哲未来人工智能研究院（IMPF-AI）。"));
};

/* ── 路由（支持 #视图 深链接） ──────────────────────────────────── */
function go(name) {
  document.querySelectorAll("#nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name));
  if (views[name] && location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  const main = $("#main");
  main.replaceChildren();
  (views[name] || views.dashboard)(main).catch((e) =>
    main.replaceChildren(el("div", { class: "card err" }, "错误：" + e.message)));
}
document.querySelectorAll("#nav button").forEach((b) =>
  b.addEventListener("click", () => go(b.dataset.view)));

async function boot() {
  try {
    const h = await api.get("/api/health");
    $("#badge-backend").textContent = "后端 " + h.backend;
    const s = await api.get("/api/stats");
    $("#badge-poems").textContent = `语料 ${s.poems} 首`;
  } catch (e) {
    $("#badge-backend").textContent = "未就绪";
  }
  const initial = location.hash.replace("#", "");
  go(views[initial] ? initial : "dashboard");
}
window.addEventListener("hashchange", () => {
  const v = location.hash.replace("#", "");
  if (views[v]) go(v);
});
boot();
