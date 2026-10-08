import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/numeric_repeat_dom.js", import.meta.url), "utf8");
const { installDOMNumericRepeat } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

function fixture(t, { value = 40, step = 1, min = 1, max = 200, direction = 1 } = {}) {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const root = new EventTarget(), host = new EventTarget();
    root.hidden = false;
    const input = { isConnected: true, disabled: false, readOnly: false };
    const state = { value, readOnly: false, ownNode: true, changes: 0 };
    function dispatch(type, props = {}, target = button, surface = root) {
        const event = new Event(type, { cancelable: true });
        Object.defineProperty(event, "target", { value: target });
        Object.assign(event, props);
        surface.dispatchEvent(event);
        return event;
    }
    const button = {
        isConnected: true, disabled: false,
        closest(selector) {
            if (selector.startsWith("button[")) return this;
            assert.equal(selector, '[node-type="IrodoriTTSGenerate"]');
            return state.ownNode ? {} : null;
        },
        parentElement: { querySelector: () => input },
        contains: (target) => target === button,
        getBoundingClientRect: () => ({ left: 10, right: 30, top: 10, bottom: 30 }),
        click(detail = 0) {
            const event = dispatch("click", { detail });
            if (!event.defaultPrevented && !this.disabled) {
                state.value = Math.max(min, Math.min(max, state.value + step * direction));
                state.changes++;
                this.disabled = direction > 0 ? state.value === max : state.value === min;
            }
        },
    };
    const dispose = installDOMNumericRepeat({ root, host, readOnly: () => state.readOnly });
    t.after(dispose);
    const down = (props) => dispatch("pointerdown", { button: 0, pointerId: 1, ...props });
    const up = () => { dispatch("pointerup", {}, button, host); button.click(1); };
    return { root, host, button, input, state, dispatch, down, up, dispose, tick: (ms) => t.mock.timers.tick(ms) };
}

test("Vue short click updates exactly once and preserves keyboard clicks", (t) => {
    const f = fixture(t);
    assert.equal(f.down().defaultPrevented, true);
    f.up(); f.tick(1000);
    assert.equal(f.state.value, 41);
    f.button.click();
    assert.equal(f.state.value, 42);
});

test("Vue hold repeats native updates at 350 ms then every 75 ms; release stops", (t) => {
    const f = fixture(t);
    f.down(); f.tick(349);
    assert.equal(f.state.value, 41);
    f.tick(1);
    for (let i = 0; i < 8; i++) f.tick(75);
    assert.equal(f.state.value, 50);
    assert.equal(f.state.changes, 10);
    f.up(); f.tick(2000);
    assert.equal(f.state.value, 50);
});

test("Vue decimal decrement stops at the native lower limit", (t) => {
    const f = fixture(t, { value: 0.2, step: 0.05, min: 0.1, direction: -1 });
    f.down(); f.tick(350); f.tick(75); f.tick(75); f.up();
    assert.equal(f.state.value, 0.1);
    assert.equal(f.button.disabled, true);
});

test("Vue integer increment stops at the native upper limit", (t) => {
    const f = fixture(t, { value: 199 });
    f.down(); f.tick(350); f.tick(2000); f.up();
    assert.equal(f.state.value, 200);
    assert.equal(f.state.changes, 1);
    assert.equal(f.down().defaultPrevented, false);
});

for (const event of ["pointerup", "pointercancel", "blur"]) {
    test(`Vue ${event} stops a hold`, (t) => {
        const f = fixture(t);
        f.down(); f.dispatch(event, {}, f.button, f.host); f.tick(1000);
        assert.equal(f.state.value, 41);
    });
}

test("Vue pointer leaving the button, Escape and hidden page stop repeat", (t) => {
    const f = fixture(t);
    f.down();
    f.dispatch("pointermove", { pointerId: 1, buttons: 1, clientX: 40, clientY: 20 }, f.button, f.host);
    f.tick(1000); assert.equal(f.state.value, 41);
    f.down(); f.dispatch("keydown", { key: "Escape" }, f.button, f.host);
    f.tick(1000); assert.equal(f.state.value, 42);
    f.down(); f.root.hidden = true; f.dispatch("visibilitychange");
    f.tick(1000); assert.equal(f.state.value, 43);
});

test("Vue removal, disabled field and read-only graph stop repeat", (t) => {
    const f = fixture(t);
    f.down(); f.button.isConnected = false; f.tick(350);
    assert.equal(f.state.value, 41);
    f.button.isConnected = true; f.down(); f.input.disabled = true; f.tick(350);
    assert.equal(f.state.value, 42);
    f.input.disabled = false; f.down(); f.state.readOnly = true; f.tick(350);
    assert.equal(f.state.value, 43);
});

test("Vue other nodes, middle click, secondary touch and text fields are untouched", (t) => {
    const f = fixture(t);
    f.state.ownNode = false; assert.equal(f.down().defaultPrevented, false);
    f.state.ownNode = true; assert.equal(f.down({ button: 1 }).defaultPrevented, false);
    assert.equal(f.down({ isPrimary: false }).defaultPrevented, false);
    assert.equal(f.dispatch("pointerdown", { button: 0 }, {}).defaultPrevented, false);
    assert.equal(f.state.value, 40);
});

test("Vue next gesture cancels the previous hold and cleanup removes listeners", (t) => {
    const f = fixture(t);
    f.down(); f.tick(200); f.down(); f.tick(350);
    assert.equal(f.state.value, 43);
    f.dispose(); f.tick(2000); f.down();
    assert.equal(f.state.value, 43);
});
