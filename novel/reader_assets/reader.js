"use strict";
const $ = id => document.getElementById(id);
let catalog = null, selected = -1, generation = 0, ready = false;
const memory = {
  get(key) { try { return localStorage.getItem("novel-reader:" + key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem("novel-reader:" + key, value); } catch {} }
};
function tell(text, error = false) { $("message").textContent = text; $("message").hidden = !text; $("message").classList.toggle("error", error); }
async function request(path) {
  const response = await fetch(path, {cache: "no-store", credentials: "same-origin"});
  let value;
  try { value = await response.json(); }
  catch { throw new Error("阅读服务暂时不可用，请稍后刷新。"); }
  if (response.status === 401) $("login-link").hidden = false;
  if (!response.ok) throw new Error(response.status === 401 ? "登录已过期，请先在服务器首页重新登录，再回到本页。" : (value.error?.message || value.error || "读取失败，请重试。"));
  return value;
}
function contentNode(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
function renderText(text, title) {
  const fragment = document.createDocumentFragment();
  if (!/^#\s+/m.test(text)) fragment.append(contentNode("h2", title));
  for (const block of text.replace(/\r\n/g, "\n").trim().split(/\n[ \t]*\n/)) {
    if (/^#{1,6}\s/.test(block)) {
      const match = block.match(/^(#{1,6})\s+([\s\S]*)$/);
      fragment.append(contentNode(match[1].length === 1 ? "h2" : "h3", match[2]));
    } else if (/^(?:\*\s*){3,}$|^-{3,}$|^_{3,}$/.test(block.trim())) {
      fragment.append(document.createElement("hr"));
    } else if (/^>\s?/.test(block)) {
      fragment.append(contentNode("blockquote", block.replace(/^>\s?/gm, "")));
    } else { fragment.append(contentNode("p", block)); }
  }
  $("manuscript").replaceChildren(fragment);
}
function navState() {
  const items = catalog.chapters;
  $("previous").disabled = !ready || selected <= 0;
  $("next").disabled = !ready || selected >= items.length - 1;
  $("previous-title").textContent = items[selected - 1]?.title || "已经是第一章";
  $("next-title").textContent = items[selected + 1]?.title || "已经是最新一章";
  $("position").textContent = items.length ? `第 ${selected + 1} / ${items.length} 章` : "暂无章节";
  $("footer-position").textContent = items.length ? `${selected + 1} / ${items.length} · ${items[selected].title}` : "暂无章节";
  $("word-count").textContent = items[selected] ? `${items[selected].characters.toLocaleString()} 字符` : "";
  document.querySelectorAll(".chapter-link").forEach((node, index) => {
    if (index === selected) node.setAttribute("aria-current", "page"); else node.removeAttribute("aria-current");
  });
}
async function openChapter(index, {restore = false, updateHash = true} = {}) {
  if (!catalog || index < 0 || index >= catalog.chapters.length) return;
  const token = ++generation, chapter = catalog.chapters[index], revision = catalog.revision;
  ready = false; selected = index; navState();
  $("manuscript").setAttribute("aria-busy", "true");
  $("manuscript").replaceChildren(contentNode("p", "正在载入章节…"));
  document.body.classList.remove("menu-open"); $("menu").setAttribute("aria-expanded", "false");
  try {
    const value = await request(`api/chapter?${new URLSearchParams({revision, id: chapter.id})}`);
    if (token !== generation) return;
    if (value.revision !== revision || value.id !== chapter.id || value.sha256 !== chapter.sha256) throw new Error("章节与目录版本不一致，请刷新版本。");
    renderText(value.text, chapter.title); ready = true; navState();
    if (updateHash) history.replaceState(null, "", `#chapter=${chapter.number}`);
    memory.set("chapter", String(chapter.number));
    document.title = `${chapter.title} · ${catalog.book.title}`;
    const offset = restore ? Number(memory.get(`scroll:${revision}:${chapter.number}`)) || 0 : 0;
    requestAnimationFrame(() => window.scrollTo({top: offset, behavior: "auto"}));
    $("manuscript").focus({preventScroll: true});
  } catch (error) {
    if (token !== generation) return;
    $("manuscript").replaceChildren(contentNode("p", "本章未能载入。请点击“刷新版本”重试。"));
    tell(error.message, true);
  } finally { if (token === generation) $("manuscript").setAttribute("aria-busy", "false"); }
}
function preferredChapter() {
  const fromUrl = new URLSearchParams(location.hash.slice(1)).get("chapter");
  return Number(fromUrl || memory.get("chapter")) || 1;
}
async function refresh(initial = false) {
  $("refresh").disabled = true;
  try {
    const value = await request("api/book"), oldRevision = catalog?.revision;
    if (!Array.isArray(value.chapters)) throw new Error("目录格式错误，请重试。");
    const preferred = initial ? preferredChapter() : catalog?.chapters[selected]?.number || 1;
    catalog = value;
    $("book-title").textContent = value.book.title;
    $("chapter-count").textContent = `${value.chapters.length} 章`;
    const date = new Date(value.checked_at).toLocaleString("zh-CN", {hour12: false});
    $("source-label").textContent = value.source_mode === "live" ? "正式工作区 · 当前版本" : "正式稿 · 核验阅读副本";
    $("version").textContent = `版本 ${value.revision.slice(0, 10)} · ${value.book.status === "accepted" ? "流程阶段通过" : "待流程复核"}`;
    $("verified-time").textContent = `核对于 ${date}`;
    const note = value.source_mode === "live" ? "" : "这是已核验的正式稿阅读副本，后续新章不会自动同步。在线正式目录接入前，可由创作助手更新副本；“刷新版本”会重新读取已有副本。";
    tell(note || (!initial && oldRevision === value.revision ? "已核对，仍为当前版本。" : !initial ? "已加载最新正式版本，继续你正在阅读的章节。" : ""));
    const fragment = document.createDocumentFragment();
    value.chapters.forEach((chapter, index) => {
      const link = document.createElement("a"); link.href = `#chapter=${chapter.number}`; link.className = "chapter-link";
      const number = contentNode("span", String(chapter.number).padStart(2, "0")); number.className = "number";
      const title = contentNode("span", chapter.title.replace(/^第[一二三四五六七八九十百零〇\d]+章[\s　·:：—-]*/, ""));
      link.append(number, title); link.addEventListener("click", event => {event.preventDefault(); openChapter(index);}); fragment.append(link);
    }); $("catalog").replaceChildren(fragment);
    if (!value.chapters.length) {
      ++generation; ready = false; selected = -1; navState();
      $("manuscript").replaceChildren(contentNode("p", "正式版本中还没有可阅读的章节。"));
      $("manuscript").setAttribute("aria-busy", "false"); return;
    }
    const found = value.chapters.findIndex(chapter => chapter.number === preferred);
    await openChapter(found < 0 ? 0 : found, {restore: initial});
  } catch (error) { tell(`刷新失败：${error.message}${catalog ? " 仍保留上次目录。" : ""}`, true); }
  finally { $("refresh").disabled = false; }
}
$("refresh").addEventListener("click", () => refresh());
$("previous").addEventListener("click", () => openChapter(selected - 1));
$("next").addEventListener("click", () => openChapter(selected + 1));
$("top").addEventListener("click", () => window.scrollTo({top: 0, behavior: "auto"}));
$("menu").addEventListener("click", () => { document.body.classList.toggle("menu-open"); $("menu").setAttribute("aria-expanded", String(document.body.classList.contains("menu-open"))); });
function fontSize(delta = 0) { const size = Math.max(17, Math.min(28, (Number(memory.get("font")) || 21) + delta)); document.documentElement.style.setProperty("--font-size", size + "px"); memory.set("font", String(size)); }
$("smaller").addEventListener("click", () => fontSize(-1)); $("larger").addEventListener("click", () => fontSize(1)); fontSize();
window.addEventListener("keydown", event => {if (!event.altKey || event.ctrlKey || event.metaKey || !ready) return; if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); openChapter(selected + (event.key === "ArrowLeft" ? -1 : 1)); }});
window.addEventListener("hashchange", () => {const number = preferredChapter(); const index = catalog?.chapters.findIndex(chapter => chapter.number === number); if (index >= 0 && index !== selected) openChapter(index, {updateHash: false});});
let scrollTimer;
window.addEventListener("scroll", () => {clearTimeout(scrollTimer); if (!ready) return; const revision = catalog.revision, number = catalog.chapters[selected].number, offset = window.scrollY; scrollTimer = setTimeout(() => memory.set(`scroll:${revision}:${number}`, String(offset)), 120);}, {passive: true});
refresh(true);
