"""Agent 1 - Browser Navigation Agent.

Owns the Playwright browser. It turns pages into structured `Observation`s,
executes actions that the Safety Agent has cleared, reveals hidden elements,
and enforces the navigation allowlist at the network layer.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, Page, Playwright, Route, sync_playwright

from ..security import is_allowed_url
from .models import Element, Observation, ProposedAction, TextBlock

log = logging.getLogger("fairclick.navigator")

_OBSERVE_JS = (Path(__file__).parent / "observe.js").read_text(encoding="utf-8")

_REVEAL_JS = """
(fcId) => {
  const el = document.querySelector(`[data-fc-id="${fcId}"]`);
  if (!el) return {strategy: 'missing'};
  const details = el.closest('details:not([open])');
  if (details) {
    const summary = details.querySelector(':scope > summary');
    if (summary) { summary.setAttribute('data-fc-reveal', '1'); return {strategy: 'click', selector: '[data-fc-reveal="1"]', how: 'opened collapsed section'}; }
  }
  // A toggle button that controls a hidden ancestor (aria-controls). Nested
  // panels are revealed outside-in: click the first controller that is visible.
  const shown = (n) => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(n).visibility !== 'hidden'; };
  let node = el.parentElement;
  while (node && node !== document.body) {
    if (node.id) {
      const ctrl = document.querySelector(`[aria-controls="${node.id}"]`);
      if (ctrl && shown(ctrl)) { ctrl.setAttribute('data-fc-reveal', '1'); return {strategy: 'click', selector: '[data-fc-reveal="1"]', how: 'expanded panel via its toggle'}; }
    }
    node = node.parentElement;
  }
  // Hover menus: hover the closest visible list item / menu container.
  node = el.parentElement;
  while (node && node !== document.body) {
    const r = node.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden') {
      node.setAttribute('data-fc-reveal', '1');
      return {strategy: 'hover', selector: '[data-fc-reveal="1"]', how: 'hovered parent menu'};
    }
    node = node.parentElement;
  }
  return {strategy: 'none'};
}
"""

_HIGHLIGHT_JS = """
(fcId) => {
  document.querySelectorAll('[data-fc-highlight]').forEach(e => { e.style.outline = e.dataset.fcPrevOutline || ''; e.removeAttribute('data-fc-highlight'); });
  if (!fcId) return false;
  const el = document.querySelector(`[data-fc-id="${fcId}"]`) || document.querySelector(`[data-fc-timer="${fcId}"]`);
  if (!el) return false;
  el.dataset.fcPrevOutline = el.style.outline;
  el.setAttribute('data-fc-highlight', '1');
  el.style.outline = '3px solid #e11d48';
  el.style.outlineOffset = '2px';
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  return true;
}
"""

_FORM_VALUES_JS = """
(formId) => {
  const form = document.querySelector(`[data-fc-form="${formId}"]`);
  if (!form) return [];
  const out = [];
  const labelOf = (el) => {
    if (el.labels && el.labels.length) return Array.from(el.labels).map(l => l.innerText).join(' ').trim();
    return el.getAttribute('aria-label') || el.placeholder || el.name || '';
  };
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    const type = (el.type || '').toLowerCase();
    if (['submit', 'button', 'reset', 'image'].includes(type)) continue;
    if ((type === 'checkbox' || type === 'radio') && !el.checked) continue;
    let value = el.value;
    if (el.tagName === 'SELECT') value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '';
    if (type === 'radio' || type === 'checkbox') value = labelOf(el) || el.value;
    out.push({ name: el.name, label: type === 'radio' ? (el.closest('fieldset')?.querySelector('legend')?.innerText || el.name) : labelOf(el), value, hidden: type === 'hidden' });
  }
  return out;
}
"""

_TIMER_JS = """(tid) => { const el = document.querySelector(`[data-fc-timer="${tid}"]`); return el ? el.innerText : null; }"""


def _timer_seconds(text: str) -> Optional[int]:
    match = re.search(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b", text or "")
    if not match:
        return None
    hours = int(match.group(1) or 0)
    return hours * 3600 + int(match.group(2)) * 60 + int(match.group(3))


class NavigationError(RuntimeError):
    pass


class BrowserNavigationAgent:
    name = "navigator"

    def __init__(self, headless: bool = True, on_blocked_request: Optional[Callable[[str], None]] = None,
                 settle_ms: int = 700, timeout_ms: int = 6000) -> None:
        self.headless = headless
        self.settle_ms = settle_ms
        self.timeout_ms = timeout_ms
        self.on_blocked_request = on_blocked_request
        self.blocked_requests: list[str] = []
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.step = 0

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(viewport={"width": 1280, "height": 860}, accept_downloads=False)
        self._context.route("**/*", self._guard_request)
        self.page = self._context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        # Dialogs (alert/confirm/prompt) raised by the site are dismissed, never accepted.
        self.page.on("dialog", lambda d: d.dismiss())
        # Popups / new tabs opened by the site are closed; the agent stays on its page.
        self._context.on("page", self._close_popup)

    def close(self) -> None:
        for closer in (lambda: self._context and self._context.close(),
                       lambda: self._browser and self._browser.close(),
                       lambda: self._pw and self._pw.stop()):
            try:
                closer()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass

    def _close_popup(self, page: Page) -> None:
        if page is not self.page:
            try:
                page.close()
            except PlaywrightError:
                pass

    def _guard_request(self, route: Route) -> None:
        url = route.request.url
        if is_allowed_url(url):
            route.continue_()
            return
        self.blocked_requests.append(url)
        if self.on_blocked_request:
            self.on_blocked_request(url)
        route.abort("blockedbyclient")

    # --------------------------------------------------------------- navigation
    def goto(self, url: str) -> None:
        if not is_allowed_url(url):
            raise NavigationError(f"Navigation outside the simulation allowlist was blocked: {url}")
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded")
        self._settle()

    def _settle(self) -> None:
        assert self.page is not None
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
        except PlaywrightError:
            pass
        # Allow delayed pop-ups / dynamic content to render before observing.
        self.page.wait_for_timeout(self.settle_ms)

    def back(self) -> None:
        assert self.page is not None
        self.page.go_back(wait_until="domcontentloaded")
        self._settle()

    # -------------------------------------------------------------- observation
    def observe(self) -> Observation:
        assert self.page is not None
        self.step += 1
        last_error: Exception | None = None
        for _ in range(3):
            try:
                raw = self.page.evaluate(_OBSERVE_JS)
                break
            except PlaywrightError as exc:  # page navigated mid-evaluation
                last_error = exc
                self._settle()
        else:
            raise NavigationError(f"Could not observe page: {last_error}")
        elements = [Element(**e) for e in raw["elements"]]
        blocks = [TextBlock(**b) for b in raw["text_blocks"]]
        return Observation(
            url=raw["url"], path=raw["path"], title=raw["title"], step=self.step,
            elements=elements, text_blocks=blocks, visible_text=raw["visible_text"],
            hidden_text=raw["hidden_text"], has_dialog=raw["has_dialog"],
            forms=raw["forms"], timers=raw["timers"],
        )

    def form_values(self, form_id: str) -> list[dict[str, Any]]:
        assert self.page is not None
        return self.page.evaluate(_FORM_VALUES_JS, form_id)

    def screenshot(self, path: Path, highlight_id: str = "", full_page: bool = False) -> Optional[str]:
        assert self.page is not None
        try:
            if highlight_id:
                self.page.evaluate(_HIGHLIGHT_JS, highlight_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path), full_page=full_page)
            return str(path)
        except PlaywrightError as exc:
            log.warning("screenshot failed: %s", exc)
            return None
        finally:
            if highlight_id:
                try:
                    self.page.evaluate(_HIGHLIGHT_JS, "")
                except PlaywrightError:
                    pass

    def probe_timer(self, timer_id: str, wait_ms: int = 1500) -> Optional[dict[str, Any]]:
        """Observe a countdown: does it tick, and does it reset when the page reloads?"""
        assert self.page is not None
        first = _timer_seconds(self.page.evaluate(_TIMER_JS, timer_id) or "")
        if first is None:
            return None
        self.page.wait_for_timeout(wait_ms)
        second = _timer_seconds(self.page.evaluate(_TIMER_JS, timer_id) or "")
        self.page.reload(wait_until="domcontentloaded")
        self._settle()
        # Timers are re-tagged by a fresh observation in the same document order.
        self.page.evaluate(_OBSERVE_JS)
        after_reload = _timer_seconds(self.page.evaluate(_TIMER_JS, timer_id) or "")
        return {"first": first, "second": second, "after_reload": after_reload,
                "ticking": second is not None and second < first,
                "reset_on_reload": after_reload is not None and second is not None and after_reload > second}

    # ---------------------------------------------------------------- execution
    def _locator(self, element: Element):
        assert self.page is not None
        return self.page.locator(f'[data-fc-id="{element.fc_id}"]')

    def _semantic_locator(self, element: Element):
        """Fallback when the tagged node disappeared (e.g. DOM re-render)."""
        assert self.page is not None
        name = (element.text or element.label).strip()
        role = {"summary": "button", "textbox": "textbox"}.get(element.role, element.role)
        if name and role in {"button", "link", "checkbox", "radio", "textbox"}:
            return self.page.get_by_role(role, name=name, exact=False).first
        if name:
            return self.page.get_by_text(name, exact=False).first
        return None

    def reveal(self, element: Element) -> str:
        assert self.page is not None
        info = self.page.evaluate(_REVEAL_JS, element.fc_id)
        strategy = info.get("strategy")
        if strategy == "click":
            self.page.locator(info["selector"]).first.click()
        elif strategy == "hover":
            self.page.locator(info["selector"]).first.hover()
        else:
            raise NavigationError(f"No way to reveal {element.descriptor}")
        self.page.evaluate("() => document.querySelectorAll('[data-fc-reveal]').forEach(e => e.removeAttribute('data-fc-reveal'))")
        self.page.wait_for_timeout(300)
        return info.get("how", strategy)

    def execute(self, action: ProposedAction, element: Optional[Element], retries: int = 2) -> str:
        """Execute a cleared action. Returns a short description of what happened."""
        assert self.page is not None
        if action.kind == "back":
            self.back()
            return "navigated back"
        if element is None:
            raise NavigationError("Action has no target element")
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            locator = self._locator(element)
            try:
                if locator.count() == 0:
                    fallback = self._semantic_locator(element)
                    if fallback is None or fallback.count() == 0:
                        raise NavigationError(f"Element disappeared: {element.descriptor}")
                    locator = fallback
                if action.kind == "reveal":
                    return self.reveal(element)
                if action.kind == "click":
                    if not locator.first.is_visible():
                        self.reveal(element)
                    locator.first.scroll_into_view_if_needed()
                    locator.first.click()
                    self._settle()
                    return f"clicked {element.descriptor}"
                if action.kind == "fill":
                    locator.first.fill(action.value)
                    return f"filled {element.descriptor}"
                if action.kind in ("check", "uncheck"):
                    desired = action.kind == "check"
                    try:
                        locator.first.set_checked(desired, timeout=2500)
                    except PlaywrightError:
                        # Visually hidden custom toggles: click the label instead.
                        locator.first.evaluate(
                            "(el, v) => { if (el.checked !== v) { (el.labels && el.labels[0] ? el.labels[0] : el).click(); } }",
                            desired)
                    return f"{action.kind}ed {element.descriptor}"
                if action.kind == "select":
                    locator.first.select_option(value=action.value)
                    return f"selected '{action.value}' in {element.descriptor}"
                raise NavigationError(f"Unsupported action: {action.kind}")
            except (PlaywrightError, NavigationError) as exc:
                last_error = exc
                log.info("action attempt %s failed: %s", attempt + 1, exc)
                time.sleep(0.3)
        raise NavigationError(f"Failed to {action.kind} {element.descriptor}: {last_error}")
