/* 诗海赫尔墨斯控制台（原生 JS 单页应用，无构建、无 CDN、离线可用） */
"use strict";

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

async function openPoem(ref) {
  const drawer = $("#drawer"), body = $("#drawer-body");
  drawer.classList.remove("hidden");
  body.textContent = "载入中…";
  try {
    const d = await api.post("/api/poem", { ref });
    if (d.error) { body.textContent = errText(d.error); return; }
    const p = d.poem;
    body.replaceChildren(
      el("h2", {}, `《${esc(p.title)}》`),
      el("div", { class: "kv" }, `${esc(p.author)} · ${esc(p.dynasty)} · ${esc(p.book)}` +
        (p.cipai ? ` · 词牌「${esc(p.cipai)}」` : "") + ` · ${esc(p.poem_id)}`),
      el("div", { class: "poemlines" },
        el("span", { class: "layer A" }, "A 原文"),
        el("div", {}, p.lines.map((ln) => el("div", {}, ln)))),
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
    );
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
    const maxAbs = Math.max(1, ...d.emotion_curve.map((v) => Math.abs(v)));
    out.replaceChildren(
      el("div", { class: "card" },
        el("h3", {}, `《${esc(d.poem.title)}》`, el("span", { class: "dim" }, `　${esc(d.poem.author)} · ${esc(d.poem.dynasty)} · ${esc(d.poem.genre)}`),
          el("span", { class: "pid", onclick: () => openPoem(d.poem.poem_id) }, " " + d.poem.poem_id)),
        ...d.lines.map((l, i) => el("div", { class: "hit" },
          el("div", { class: "t", style: "font-size:17px" }, l.line),
          el("div", { class: "meta" },
            el("span", { class: "layer B" }, l.tone_pattern || "—"),
            l.imagery.length ? "　意象：" + l.imagery.join("、") : "",
            l.emotions.length ? "　情感：" + l.emotions.join("、") : "",
            l.negated.length ? "　（否定：" + l.negated.join("、") + "）" : ""),
          l.allusions.length ? el("div", { class: "kv" },
            "📜 " + l.allusions.map((a) => `${a.allusion}（${a.source}→${a.implies}）`).join("；")) : null,
          el("div", { style: `height:5px;width:${Math.abs(d.emotion_curve[i]) / maxAbs * 60 + 2}%;` +
            `background:${d.emotion_curve[i] >= 0 ? "var(--accent2)" : "var(--bad)"};border-radius:2px;margin-top:4px` })))),
      d.couplets && d.couplets.length ? el("div", { class: "card" }, el("h3", {}, "对仗（B层启发式）"),
        d.couplets.map((c) => el("div", { class: "kv" },
          `${c.couplet}：${c.verdict}｜平仄相对率 ${c.tone_opposition_rate}｜范畴对位率 ${c.category_match_rate ?? "—"}`))) : null,
      el("div", { class: "card dim" }, esc(d.note)));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "进入一首诗（逐句诗境：意象/情感/平仄/典故 + 情感曲线）"),
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
      (r.co_imagery || []).map((c) => el("span", { class: "tag", onclick: () => { input.value = c.imagery; run(c.imagery); } }, `${c.imagery} ${c.count}`))));
  };
  runImagery = run;
  main.replaceChildren(el("h2", {}, "意象档案（跨诗归纳 + 证据链）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: () => run() }, "查询")), out);
};

views.cipai = async (main) => {
  const input = el("input", { placeholder: "浣溪沙 / 菩萨蛮 / 水调歌头…" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/cipai", { cipai: input.value });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const r = d.cipai_profile;
    out.replaceChildren(el("div", { class: "card" },
      el("h3", {}, `词牌「${esc(r.cipai)}」（语料 ${r.n_poems} 首）`),
      el("div", { class: "kv" },
        `众数句式：${esc(r.char_pattern)}`, el("br"),
        `一致率：${Math.round(r.pattern_consistency * 100)}%｜众数句数：${r.line_count_mode}`, el("br"),
        el("i", {}, esc(r.note))),
      el("h3", {}, "例词"),
      (r.example_poems || []).map((p) => el("div", { class: "hit" },
        el("div", { class: "t" }, `《${esc(p.title)}》`, el("span", { class: "dim" }, `　${esc(p.author)}`)),
        el("span", { class: "pid", onclick: () => openPoem(p.poem_id) }, p.poem_id)))));
  };
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") run(); });
  main.replaceChildren(el("h2", {}, "词牌定格（语料归纳，非词谱权威表）"),
    el("div", { class: "row" }, input, el("button", { class: "go", onclick: run }, "查询")), out);
};

views.author = async (main) => {
  const input = el("input", { placeholder: "李白 / 杜甫 / 李清照 / 纳兰性德…" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/author", { author: input.value });
    if (d.error) { out.replaceChildren(el("div", { class: "card err" }, errText(d.error))); return; }
    const r = d.author_profile;
    out.replaceChildren(el("div", { class: "card" },
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
  main.replaceChildren(el("h2", {}, "诗人档案"),
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

views.rhyme = async (main) => {
  const input = el("input", { placeholder: "单字，如：天 / 秋 / 愁", maxlength: "2" });
  const out = el("div", {});
  const run = async () => {
    out.replaceChildren(el("div", { class: "card" }, "查询中…"));
    const d = await api.post("/api/rhyme", { char: input.value });
    out.replaceChildren(el("div", { class: "card" },
      el("div", { class: "kv" }, el("i", {}, esc(d.note))),
      ...(d.groups || []).map((g) => el("div", { class: "card" },
        el("h3", {}, `韵组【${esc(g.label)}】 · ${g.members.length} 字 · 支撑 ${g.n_poems} 首`),
        el("div", { class: "answer" }, (g.members || []).join(" ")),
        el("div", { class: "kv" }, "高频共现对：" + (g.edge_examples || []).slice(0, 6)
          .map((e2) => `${e2.pair.join("")}×${e2.co_occurrence}`).join("｜")))),
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
      el("div", { style: `height:6px;width:${w}%;background:var(--accent2);border-radius:3px;margin:2px 0 6px` }));
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
      "· 可选接入 Anthropic/OpenAI 等真实大模型（LiteLLM），所有生成内容过引用核验\n\n" +
      "数据源（三源实质纳入）：chinese-poetry（MIT，A层核心语料）；" +
      "PoetryMTEB（D层外部分析，3,084 首双向回源绑定）；" +
      "gujilab/chinese-classical-corpus（CC0，说文解字 9,829 条 + 尔雅训释 → C层训诂）；" +
      "OpenCC 字表（简繁归一）。\n架构参照：Shanghan-Hermes（伤寒-赫尔墨斯）。"));
};

/* ── 路由 ───────────────────────────────────────────────────────── */
function go(name) {
  document.querySelectorAll("#nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name));
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
  go("dashboard");
}
boot();
