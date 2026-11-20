# Vimium Refinement: Source of Truth

Personal fork of philc/vimium. This file is the only place where goals, decisions, findings and status are tracked. Update it before and after every change.

Legend: `[ ]` todo, `[x]` done, `[~]` in progress, `[-]` dropped.
Confidence: **Confirmed** (seen in code), **Likely** (inferred, depends on page behavior), **Unverified** (needs a file or a test).

---

## 1. Goals

- [ ] **G1.** On claude.ai, `Esc` leaves the message box **without stopping the chat**, and `j`/`k` work right afterwards.
- [ ] **G2.** Selecting text (visual mode) is easy and starts where I am looking, not in the message box or at the top of the page.
- [ ] **G3.** `j`/`k` scroll side panels without having to click inside them first.

## 2. Decisions (do not revisit without a reason)

| # | Decision | Status |
|---|----------|--------|
| D1 | Do **not** use Alt+j / Alt+k as a workaround. The fix must make plain `j`/`k` work. | Final |
| D2 | `Esc` must blur the input and must not reach the page as a stop signal. | Final |
| D3 | Never rewrite whole files. Changes are small FIND/REPLACE patches. | Final |
| D4 | Side-panel scroll change: apply on all sites or only claude.ai? | **Open** (see section 7) |

## 3. Findings (root causes)

### F1. Insert mode swallows `j`, `k`, `v` in the chat box
- **Confidence: Confirmed.**
- `lib/dom_utils.js`: `isEditable()` returns true for any `contenteditable` element; `isFocusable()` includes it.
- `content_scripts/mode_insert.js`: `isActive()` is true whenever the active element is focusable, and `handleKeyEvent` passes every key except `Esc` to the page.
- Claude's message box is focused automatically, so Vimium stays in insert mode.

### F2. `Esc` stops the chat
- **Confidence: Likely.** Vimium side is confirmed, page side is not.
- `mode_insert.js`: `handleKeyEvent` is registered for `keypress` and `keydown` only. There is no `keyup` handler, so the Escape keyup always reaches the page.
- Not provable from Vimium's code: how claude.ai listens for Escape.

### F3. Why `f` then click, then `j` works
- **Confidence: Confirmed.**
- The click moves focus out of the box (insert mode ends) and sets `activatedElement` in `scroller.js` to the clicked element, so scrolling starts inside the chat's scroll container.

### F4. Visual mode is hard to enter
- **Confidence: Confirmed** for (a) and (b), **Likely** for (c).
- (a) `v` is typed into the box while insert mode is active (same cause as F1).
- (b) `VisualMode.init` in `mode_visual.js` keeps a `Caret` selection that is visible in the viewport. After `Esc`, the caret often stays in the message box. Extending by one character fails on an empty or short editor, so visual mode falls back to caret mode inside the box.
- (c) Claude's page re-renders while streaming and may clear a selection. Needs a live test.
- `CaretMode.establishInitialSelectionAnchor` takes the first visible, non-editable text node with at least 50 characters in DOM order. It ignores the mouse position and the viewport focus, so it can choose a sidebar item.

### F5. Side panels do not scroll
- **Confidence: Confirmed.**
- `scroller.js`: scrolling starts at `activatedElement`, or at `firstScrollableElement()` (largest visible scrollable area, i.e. the main chat) if nothing was clicked.
- `findScrollableElement` only walks **up** through parents (`DomUtils.getContainingElement`). A sibling panel is never reached.
- `vimium_frontend.js`: `checkEnabledAfterURLChange` calls `Scroller.reset()`, so the panel is forgotten after navigation.

## 4. Planned changes

| ID | Goal | File | Change | Status |
|----|------|------|--------|--------|
| C1 | G1 | `content_scripts/mode_insert.js` | Also consume the Escape keyup (use `DomUtils.consumeKeyup`) so the page never sees a full Esc press. | [~] |
| C2 | G1 | `content_scripts/mode_insert.js` or `lib/dom_utils.js` | On claude.ai only, do not treat the message box as an active insert target until clicked or `i` is pressed. | [~] |
| C3 | G2 | `content_scripts/mode_visual.js` | If the selection is a caret inside an editable element, clear it before starting visual mode. | [~] |
| C4 | G2 | `content_scripts/mode_visual.js` | In `establishInitialSelectionAnchor`, prefer visible text under or near the mouse pointer, then fall back to DOM order. | [~] |
| C5 | G3 | `content_scripts/scroller.js` | Track the last mouse position; scroll the scrollable element under the pointer first, then fall back to current behavior. Pointer is only preferred if the mouse moved after the last click. | [~] |
| C6 | G3 | `content_scripts/vimium_frontend.js` | Optional: do not lose the pointer-based target on `Scroller.reset()`. Not needed: the pointer position is stored outside `reset()`. | [-] |

Files that may be touched: `content_scripts/mode_insert.js`, `content_scripts/mode_visual.js`, `content_scripts/scroller.js`, `content_scripts/vimium_frontend.js`, `lib/dom_utils.js`. Do not edit anything else without adding it here first.

## 5. Test checklist (manual, on claude.ai)

Run after every change. Test with the chat idle **and** while a reply is streaming.

**Esc and focus**
- [ ] Click the message box, press `Esc`: box loses focus.
- [ ] Press `Esc` while a reply is streaming: the reply keeps generating.
- [ ] After `Esc`, press `j` and `k`: the conversation scrolls.
- [ ] Click the box and type text including the letters `j`, `k`, `v`: they are typed normally.
- [ ] Press `i`: insert mode works as before.

**Visual mode**
- [ ] After `Esc`, press `v`: visual mode starts, and the selection is not inside the message box.
- [ ] Press `v` with the mouse over a message: selection starts near that message.
- [ ] `y` yanks the selected text, `Esc` exits cleanly.
- [ ] `V` (line mode) and `c` (caret mode) still work.
- [ ] A selection made by mouse is kept when pressing `v`.

**Scrolling**
- [ ] Mouse over a side panel, press `j`/`k`: the panel scrolls.
- [ ] Mouse over the main chat, press `j`/`k`: the chat scrolls.
- [ ] After navigating to another conversation, scrolling still works without clicking.
- [ ] `gg`, `G`, `d`, `u` still scroll the right element.

**Regression (other sites)**
- [ ] A plain page (e.g. a Wikipedia article): `j`/`k`/`v` unchanged.
- [ ] A site with an input (e.g. a search box): typing still works, `Esc` still blurs.
- [ ] Reddit or another site in the scroller's special-case list still scrolls.
- [ ] Link hints (`f`) and the omnibar (`o`) still work.

## 6. Setup and workflow

- [ ] Fork or clone philc/vimium into a local folder.
- [ ] Disable the store version of Vimium while testing.
- [ ] Chrome/Edge: `chrome://extensions` > Developer mode > Load unpacked. Firefox: `about:debugging#/runtime/this-firefox` > Load Temporary Add-on > `manifest.json`.
- [ ] After each patch, click the extension's reload icon, then reload the claude.ai tab.
- [ ] Run the repo's own tests if available (`tests/unit_tests`, `tests/dom_tests`) before keeping a change.
- [ ] Commit one change (C1, C2, ...) at a time so any of them can be reverted alone.

## 7. Open questions

- [ ] Should C5 (pointer-based scrolling) apply to all sites or only claude.ai? (D4) Currently all sites; set `pointerScrollHosts` in `scroller.js` to restrict it.
- [ ] Does claude.ai react to Escape on `keydown`, `keyup`, or both? Check in DevTools (Event Listeners on `document`/`window`) to turn F2 from Likely into Confirmed.
- [ ] Does claude.ai clear or move the selection while streaming? Test for F4(c).
- [ ] How to detect the claude.ai message box reliably (attribute, role, or class) without depending on a class name that may change?

## 8. Change log

| Date | Change | Result |
|------|--------|--------|
| 2026-11-20 | C1-C5 patched in `mode_insert.js`, `mode_visual.js`, `scroller.js`, `lib/dom_utils.js`; C6 dropped | Untested, run section 5 |
