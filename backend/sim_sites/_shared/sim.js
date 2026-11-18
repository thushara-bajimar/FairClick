// Shared helpers for the simulated (deliberately manipulative) websites.
(function () {
  const params = new URLSearchParams(location.search);

  // <span data-param="ref"></span> -> filled from ?ref=... (textContent only - no HTML injection).
  document.querySelectorAll("[data-param]").forEach((el) => {
    const v = params.get(el.getAttribute("data-param"));
    if (v) el.textContent = v;
  });

  // <a data-carry="order"> appends ?order=<current value> to its href.
  document.querySelectorAll("[data-carry]").forEach((el) => {
    const key = el.getAttribute("data-carry");
    const v = params.get(key);
    if (v && el.href) {
      const u = new URL(el.href);
      u.searchParams.set(key, v);
      el.href = u.toString();
    }
  });

  // Fake countdowns: <span data-countdown="119"> - restarts from the same value on every page load.
  document.querySelectorAll("[data-countdown]").forEach((el) => {
    let left = parseInt(el.getAttribute("data-countdown"), 10);
    const fmt = (s) => {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
      const mm = String(m).padStart(2, "0"), ss = String(sec).padStart(2, "0");
      return h ? `${String(h).padStart(2, "0")}:${mm}:${ss}` : `${mm}:${ss}`;
    };
    el.textContent = fmt(left);
    setInterval(() => { left = Math.max(0, left - 1); el.textContent = fmt(left); }, 1000);
  });

  // Toggle panels: <button aria-controls="id" aria-expanded="false">
  document.querySelectorAll("button[aria-controls]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const target = document.getElementById(btn.getAttribute("aria-controls"));
      if (!target) return;
      e.preventDefault();
      const open = target.hasAttribute("hidden");
      if (open) target.removeAttribute("hidden"); else target.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", String(open));
    });
  });

  // Delayed pop-ups: <div data-popup-delay="700" hidden role="dialog">
  document.querySelectorAll("[data-popup-delay]").forEach((el) => {
    setTimeout(() => el.removeAttribute("hidden"), parseInt(el.getAttribute("data-popup-delay"), 10));
    el.querySelectorAll("[data-close-popup]").forEach((b) => b.addEventListener("click", () => el.setAttribute("hidden", "")));
  });

  // Consent result pages: render ?analytics=0/1 ... into "Category: On/Off" lines.
  const list = document.getElementById("consent-state");
  if (list) {
    const names = { analytics: "Analytics", advertising: "Personalised advertising", social: "Social media tracking", personalisation: "Content personalisation", partners: "Legitimate-interest partners" };
    const necessary = document.createElement("li");
    necessary.textContent = "Strictly necessary: On (required)";
    list.appendChild(necessary);
    Object.keys(names).forEach((k) => {
      if (!params.has(k)) return;
      const li = document.createElement("li");
      li.textContent = `${names[k]}: ${params.get(k) === "1" ? "On" : "Off"}`;
      list.appendChild(li);
    });
  }
})();
