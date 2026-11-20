class InsertMode extends Mode {
  constructor(options) {
    super();
    if (options == null) {
      options = {};
    }

    // There is one permanently-installed instance of InsertMode. It tracks focus changes and
    // activates/deactivates itself (by setting @insertModeLock) accordingly.
    this.permanent = options.permanent;

    // If truthy, then we were activated by the user (with "i").
    this.global = options.global;

    this.passNextKeyKeys = [];

    // This list of keys is parsed from the user's key mapping config by commands.js, and stored in
    // chrome.storage.session.
    chrome.storage.session.get("passNextKeyKeys").then((value) => {
      this.passNextKeyKeys = value.passNextKeyKeys || [];
    });

    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName != "local") {
        return;
      }
      if (changes.passNextKeyKeys == null) {
        return;
      }
      this.passNextKeyKeys = changes.passNextKeyKeys.newValue;
    });

    const handleKeyEvent = (event) => {
      if (!this.isActive(event)) {
        return this.continueBubbling;
      }

      // See comment here:
      // https://github.com/philc/vimium/commit/48c169bd5a61685bb4e67b1e76c939dbf360a658
      const activeElement = this.getActiveElement();
      if ((activeElement === document.body) && activeElement.isContentEditable) {
        return this.passEventToPage;
      }

      // Check for a pass-next-key key.
      const keyString = KeyboardUtils.getKeyCharString(event);
      if (this.passNextKeyKeys.includes(keyString)) {
        new PassNextKeyMode();
      } else if ((event.type === "keydown") && KeyboardUtils.isEscape(event)) {
        // C1: also swallow the matching keyup, so the page never sees a complete Esc press.
        DomUtils.consumeKeyup(event);
        if (DomUtils.isFocusable(activeElement)) {
          activeElement.blur();
        }

        if (!this.permanent) {
          this.exit();
        }
      } else {
        return this.passEventToPage;
      }

      return this.suppressEvent;
    };

    const defaults = {
      name: "insert",
      indicator: !this.permanent && !Settings.get("hideHud") ? "Insert mode" : null,
      keypress: handleKeyEvent,
      keydown: handleKeyEvent,
    };

    super.init(Object.assign(defaults, options));

    if (this.permanent) {
      // C2: remember which editable element the user deliberately engaged (see
      // isUnengagedClaudeBox).
      this.push({
        _name: "insert/track-engaged-element",
        mousedown: (event) =>
          this.alwaysContinueBubbling(() => {
            if (
              (event.target instanceof Element) &&
              (event.target.isContentEditable || DomUtils.isEditable(event.target))
            ) {
              InsertMode.engagedElement = event.target;
            }
          }),
        blur: (event) =>
          this.alwaysContinueBubbling(() => {
            const engaged = InsertMode.engagedElement;
            if (engaged && (event.target instanceof Element) && event.target.contains(engaged)) {
              InsertMode.engagedElement = null;
            }
          }),
      });
    }

    // Only for tests. This gives us a hook to test the status of the permanently-installed
    // instance.
    if (this.permanent) {
      InsertMode.permanentInstance = this;
    }
  }

  isActive(event) {
    if (event === InsertMode.suppressedEvent) {
      return false;
    }
    if (this.global) {
      return true;
    }
    const activeElement = this.getActiveElement();
    if (InsertMode.isUnengagedClaudeBox(activeElement)) {
      // Stay passive so j/k/v work, but still let Escape through so it blurs the box.
      return (event != null) && (event.type === "keydown") && KeyboardUtils.isEscape(event);
    }
    return DomUtils.isFocusable(activeElement);
  }

  getActiveElement() {
    let activeElement = document.activeElement;
    while (activeElement && activeElement.shadowRoot && activeElement.shadowRoot.activeElement) {
      activeElement = activeElement.shadowRoot.activeElement;
    }
    return activeElement;
  }

  static suppressEvent(event) {
    return this.suppressedEvent = event;
  }

  // On claude.ai the message box is focused automatically, which would keep Vimium in insert mode
  // permanently. Treat it as an insert target only after the user clicked it, focused it with a
  // Vimium command, or pressed `i`.
  static isUnengagedClaudeBox(element) {
    // Applies to every chat site in DomUtils.chatHosts. The message box is either a
    // contenteditable (Claude, ChatGPT) or a plain textarea (DeepSeek).
    if (!DomUtils.isChatHost()) {
      return false;
    }
    if (!element) {
      return false;
    }
    const isMessageBox = element.isContentEditable ||
      (element.nodeName?.toLowerCase() === "textarea");
    if (!isMessageBox) {
      return false;
    }
    const engaged = InsertMode.engagedElement;
    return !(engaged && element.contains(engaged));
  }
}

// This allows PostFindMode to suppress the permanently-installed InsertMode instance.
InsertMode.suppressedEvent = null;

// The editable element the user last deliberately engaged (clicked or focused via Vimium).
InsertMode.engagedElement = null;

// This implements the pasNexKey command.
class PassNextKeyMode extends Mode {
  constructor(count) {
    if (count == null) {
      count = 1;
    }
    super();
    let seenKeyDown = false;
    let keyDownCount = 0;

    super.init({
      name: "pass-next-key",
      indicator: "Pass next key.",
      // We exit on blur because, once we lose the focus, we can no longer track key events.
      exitOnBlur: globalThis,
      keypress: () => {
        return this.passEventToPage;
      },

      keydown: () => {
        seenKeyDown = true;
        keyDownCount += 1;
        return this.passEventToPage;
      },

      keyup: () => {
        if (seenKeyDown) {
          if (!(--keyDownCount > 0)) {
            if (!(--count > 0)) {
              this.exit();
            }
          }
        }
        return this.passEventToPage;
      },
    });
  }
}

globalThis.InsertMode = InsertMode;
globalThis.PassNextKeyMode = PassNextKeyMode;
