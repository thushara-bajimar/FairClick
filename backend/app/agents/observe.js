// Injected by the Browser Navigation Agent to build a structured observation of
// the current page. It only *reads* the page (plus tagging elements with a
// data-fc-id attribute so they can be located again); it never clicks.
() => {
  const MAX_ELEMENTS = 250;
  const MAX_BLOCKS = 400;

  const parseColor = (str) => {
    const m = (str || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((v) => parseFloat(v));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const luminance = (c) => {
    const ch = [c.r, c.g, c.b].map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };
  const effectiveBackground = (el) => {
    let node = el;
    while (node && node.nodeType === 1) {
      const bg = parseColor(getComputedStyle(node).backgroundColor);
      if (bg && bg.a > 0.5) return bg;
      node = node.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  };
  const contrastOf = (el) => {
    const style = getComputedStyle(el);
    const fg = parseColor(style.color) || { r: 0, g: 0, b: 0, a: 1 };
    const bg = effectiveBackground(el);
    const l1 = luminance(fg), l2 = luminance(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    return Math.round(ratio * 100) / 100;
  };
  const effectiveOpacity = (el) => {
    let o = 1, node = el;
    while (node && node.nodeType === 1) {
      o *= parseFloat(getComputedStyle(node).opacity || "1");
      node = node.parentElement;
    }
    return Math.round(o * 100) / 100;
  };
  const isRendered = (el) => {
    let node = el;
    while (node && node.nodeType === 1) {
      const s = getComputedStyle(node);
      if (s.display === "none" || s.visibility === "hidden" || s.visibility === "collapse") return false;
      if (node !== el && node.tagName === "DETAILS" && !node.open) {
        // Content of a closed <details> (except its own summary) is not rendered.
        const summary = node.querySelector(":scope > summary");
        if (!(summary && (summary === el || summary.contains(el)))) return false;
      }
      node = node.parentElement;
    }
    return true;
  };
  const isVisible = (el) => {
    if (!isRendered(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (effectiveOpacity(el) < 0.05) return false;
    return true;
  };
  const regionOf = (el) => {
    if (el.closest("[role=dialog], dialog, [aria-modal=true]")) return "dialog";
    if (el.closest("[role=alertdialog], [data-banner], [role=region][aria-label*=ookie i]")) return "banner";
    if (el.closest("footer, [role=contentinfo]")) return "footer";
    if (el.closest("nav, [role=navigation]")) return "nav";
    if (el.closest("header, [role=banner]")) return "header";
    return "main";
  };
  const labelFor = (el) => {
    const parts = [];
    if (el.labels && el.labels.length) parts.push(...Array.from(el.labels).map((l) => (l.innerText || l.textContent || "").trim()));
    if (el.getAttribute("aria-label")) parts.push(el.getAttribute("aria-label"));
    const lb = el.getAttribute("aria-labelledby");
    if (lb) lb.split(/\s+/).forEach((id) => { const t = document.getElementById(id); if (t) parts.push(t.innerText || t.textContent); });
    if (!parts.length && el.placeholder) parts.push(el.placeholder);
    if (!parts.length && el.title) parts.push(el.title);
    if ((el.type === "radio") && el.closest("fieldset")) {
      const legend = el.closest("fieldset").querySelector("legend");
      if (legend) parts.push("[group: " + (legend.innerText || legend.textContent) + "]");
    }
    return parts.join(" ").replace(/\s+/g, " ").trim();
  };
  const roleOf = (el) => {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "select";
    if (tag === "textarea") return "textbox";
    if (tag === "summary") return "summary";
    if (tag === "input") {
      const t = (el.type || "text").toLowerCase();
      if (t === "checkbox") return "checkbox";
      if (t === "radio") return "radio";
      if (t === "submit" || t === "button" || t === "reset" || t === "image") return "button";
      return "textbox";
    }
    return "button";
  };

  // Clear tags from the previous observation.
  document.querySelectorAll("[data-fc-id]").forEach((e) => e.removeAttribute("data-fc-id"));
  document.querySelectorAll("[data-fc-form]").forEach((e) => e.removeAttribute("data-fc-form"));
  document.querySelectorAll("[data-fc-timer]").forEach((e) => e.removeAttribute("data-fc-timer"));

  const forms = [];
  document.querySelectorAll("form").forEach((f, i) => {
    const id = "f" + i;
    f.setAttribute("data-fc-form", id);
    forms.push({
      id,
      method: (f.getAttribute("method") || "get").toLowerCase(),
      action: f.action || location.href,
      name: f.getAttribute("name") || f.getAttribute("aria-label") || "",
      hidden_fields: Array.from(f.querySelectorAll("input[type=hidden]")).map((h) => ({ name: h.name, value: h.value })),
    });
  });

  const selector = "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=checkbox], [role=switch], [role=menuitem]";
  const elements = [];
  let n = 0;
  for (const el of document.querySelectorAll(selector)) {
    if (n >= MAX_ELEMENTS) break;
    const id = "e" + n++;
    el.setAttribute("data-fc-id", id);
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const tag = el.tagName.toLowerCase();
    const role = roleOf(el);
    let visible = isVisible(el);
    // Custom toggle switches often hide the real checkbox; treat it as visible
    // when its label is visible.
    if (!visible && (role === "checkbox" || role === "radio") && el.labels && el.labels.length && isRendered(el)) {
      visible = Array.from(el.labels).some((l) => isVisible(l));
    }
    const form = el.form || el.closest("form");
    let text = "";
    if (tag === "input" || tag === "select" || tag === "textarea") {
      text = (tag === "input" && ["submit", "button"].includes((el.type || "").toLowerCase())) ? el.value : "";
    } else {
      text = (el.innerText || el.textContent || "").trim();
    }
    if (!text) text = el.getAttribute("aria-label") || el.title || "";
    const closedDetails = el.closest("details:not([open])");
    const insideClosed = !!closedDetails && !(tag === "summary" && el.parentElement === closedDetails);
    const options = tag === "select" ? Array.from(el.options).map((o) => ({ value: o.value, text: o.text.trim(), selected: o.selected })) : [];
    const isSubmit = !!form && ((tag === "button" && (el.type || "submit") === "submit") || (tag === "input" && ["submit", "image"].includes((el.type || "").toLowerCase())));
    elements.push({
      fc_id: id,
      tag,
      role,
      text: text.replace(/\s+/g, " ").trim().slice(0, 200),
      href: tag === "a" ? el.href : "",
      input_type: tag === "input" ? (el.type || "text").toLowerCase() : "",
      name: el.getAttribute("name") || "",
      label: labelFor(el).slice(0, 300),
      value: (tag === "input" || tag === "textarea" || tag === "select") ? (el.value || "") : "",
      checked: (el.type === "checkbox" || el.type === "radio") ? el.checked : (el.getAttribute("aria-checked") ? el.getAttribute("aria-checked") === "true" : null),
      required: !!el.required || el.getAttribute("aria-required") === "true",
      disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
      visible,
      in_viewport: rect.top < window.innerHeight && rect.bottom > 0,
      inside_closed_details: insideClosed,
      inside_dialog: !!el.closest("[role=dialog], dialog, [aria-modal=true]"),
      form_id: form ? form.getAttribute("data-fc-form") || "" : "",
      form_method: form ? (form.getAttribute("method") || "get").toLowerCase() : "",
      form_action: form ? (el.getAttribute("formaction") ? new URL(el.getAttribute("formaction"), location.href).href : form.action) : "",
      is_submit: isSubmit,
      options,
      font_size: parseFloat(style.fontSize) || 0,
      font_weight: parseInt(style.fontWeight, 10) || 400,
      color: style.color,
      background: style.backgroundColor,
      contrast: contrastOf(el),
      opacity: effectiveOpacity(el),
      area: Math.round(rect.width * rect.height),
      x: Math.round(rect.left + window.scrollX),
      y: Math.round(rect.top + window.scrollY),
      region: regionOf(el),
    });
  }

  // Text blocks: group text nodes by their parent element.
  const blocks = new Map();
  const hiddenParts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const t = node.textContent.replace(/\s+/g, " ").trim();
    if (!t) continue;
    const parent = node.parentElement;
    if (!parent || ["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(parent.tagName)) continue;
    if (blocks.has(parent)) { blocks.get(parent).text += " " + t; continue; }
    if (blocks.size >= MAX_BLOCKS) continue;
    blocks.set(parent, { text: t, el: parent });
  }
  const textBlocks = [];
  for (const { text, el } of blocks.values()) {
    const style = getComputedStyle(el);
    const visible = isVisible(el);
    const contrast = contrastOf(el);
    const fontSize = parseFloat(style.fontSize) || 0;
    // Text that is in the DOM but invisible to people (display:none, tiny or
    // same-colour-as-background) is collected separately for injection screening.
    if (!visible || contrast < 1.3 || fontSize < 4) hiddenParts.push(text);
    textBlocks.push({
      text: text.slice(0, 600),
      tag: el.tagName.toLowerCase(),
      font_size: fontSize,
      contrast,
      visible,
      region: regionOf(el),
      fc_id: el.getAttribute("data-fc-id") || "",
    });
  }

  // Countdown-looking timers (mm:ss or hh:mm:ss).
  const timers = [];
  let ti = 0;
  for (const tb of blocks.values()) {
    // Only short, countdown-like text (not e.g. "Scheduled arrival 14:05").
    if (/^\D{0,3}\d{1,2}:\d{2}(:\d{2})?\D{0,3}$/.test(tb.text.trim()) && isVisible(tb.el)) {
      const tid = "t" + ti++;
      tb.el.setAttribute("data-fc-timer", tid);
      timers.push({ id: tid, text: tb.text });
    }
  }

  const hasDialog = Array.from(document.querySelectorAll("[role=dialog], dialog[open], [aria-modal=true]")).some((d) => isVisible(d));

  return {
    url: location.href,
    path: location.pathname,
    title: document.title,
    elements,
    text_blocks: textBlocks,
    visible_text: (document.body.innerText || "").slice(0, 20000),
    hidden_text: hiddenParts.join(" \n").slice(0, 5000),
    has_dialog: hasDialog,
    forms,
    timers,
  };
}
