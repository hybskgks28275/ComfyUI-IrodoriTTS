import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/numeric_repeat_core.js", import.meta.url), "utf8");
const { installNumericRepeat } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

function fixture(t, { value = 40, step = 1, min = 1, max = 200, x = 375 } = {}) {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    globalThis.window = new EventTarget();
    globalThis.document = new EventTarget();
    document.hidden = false;
    const graph = { begin: 0, end: 0, beforeChange() { this.begin++; }, afterChange() { this.end++; } };
    const node = { pos: [0, 0], size: [400, 700], graph, setDirtyCanvas() {} };
    const canvas = { graph, read_only: false };
    const pointer = { isDown: true, eDown: { button: 0, canvasX: x, canvasY: 120 } };
    const widget = {
        type: "number", value,
        incrementValue() { this.value = Math.min(max, this.value + step); },
        decrementValue() { this.value = Math.max(min, this.value - step); },
    };
    const dispose = installNumericRepeat(widget);
    t.after(dispose);
    const down = () => widget.onPointerDown(pointer, node, canvas);
    const up = () => { window.dispatchEvent(new Event("pointerup")); pointer.isDown = false; pointer.onClick?.(); pointer.finally?.(); };
    const tick = (ms) => t.mock.timers.tick(ms);
    return { graph, node, canvas, pointer, widget, down, up, tick, dispose };
}

test("short click increments once and release does not increment again", (t) => {
    const f = fixture(t);
    assert.equal(f.down(), true);
    assert.equal(f.widget.value, 41);
    f.tick(349);
    assert.equal(f.widget.value, 41);
    f.up();
    f.tick(1000);
    assert.equal(f.widget.value, 41);
    assert.deepEqual([f.graph.begin, f.graph.end], [1, 1]);
});

test("holding repeats after delay until released", (t) => {
    const f = fixture(t);
    f.down(); f.tick(350);
    assert.equal(f.widget.value, 42);
    for (let i = 0; i < 8; i++) f.tick(75);
    assert.equal(f.widget.value, 50);
    f.up(); f.tick(5000);
    assert.equal(f.widget.value, 50);
});

test("left arrow delegates fractional steps and respects the lower bound", (t) => {
    const f = fixture(t, { value: 0.2, step: 0.05, min: 0.1, x: 25 });
    f.down(); f.tick(350); f.tick(75); f.tick(75);
    assert.equal(f.widget.value, 0.1);
    assert.equal(f.graph.end, 1);
});

test("upper bound stops repeat without overrunning", (t) => {
    const f = fixture(t, { value: 199 });
    f.down(); f.tick(350); f.tick(1000);
    assert.equal(f.widget.value, 200);
    assert.equal(f.graph.end, 1);
});

for (const event of ["blur", "pointercancel", "pointerdown"]) {
    test(`${event} stops a pending repeat`, (t) => {
        const f = fixture(t);
        f.down(); window.dispatchEvent(new Event(event)); f.tick(1000);
        assert.equal(f.widget.value, 41);
        assert.equal(f.graph.end, 1);
    });
}

test("hidden page and Escape stop repeating", (t) => {
    const f = fixture(t);
    f.down(); document.hidden = true;
    document.dispatchEvent(new Event("visibilitychange")); f.tick(1000);
    assert.equal(f.widget.value, 41);
    document.hidden = false;
    f.down();
    const event = new Event("keydown"); event.key = "Escape";
    window.dispatchEvent(event); f.tick(1000);
    assert.equal(f.widget.value, 42);
});

test("removing the node or replacing its graph stops repeating", (t) => {
    const f = fixture(t);
    f.down(); f.node.graph = null; f.tick(350);
    assert.equal(f.widget.value, 41);
    f.node.graph = f.graph;
    f.down(); f.dispose(); f.tick(1000);
    assert.equal(f.widget.value, 42);
    assert.equal(f.widget.onPointerDown, undefined);
});

test("small pointer drift is allowed; leaving the arrow stops the hold", (t) => {
    const f = fixture(t);
    f.down(); f.pointer.onDragStart();
    f.pointer.onDrag({ canvasX: 376, canvasY: 121 }); f.tick(350);
    assert.equal(f.widget.value, 42);
    f.pointer.onDrag({ canvasX: 200, canvasY: 120 }); f.tick(1000);
    assert.equal(f.widget.value, 42);
});

test("center, disabled widgets and read-only canvas retain native handling", (t) => {
    const f = fixture(t, { x: 200 });
    assert.equal(f.down(), false);
    f.pointer.eDown.canvasX = 375; f.widget.disabled = true;
    assert.equal(f.down(), false);
    f.widget.disabled = false; f.canvas.read_only = true;
    assert.equal(f.down(), false);
    f.tick(1000);
    assert.equal(f.widget.value, 40);
});

test("non-numeric widgets are left untouched", () => {
    const widget = { type: "combo" };
    installNumericRepeat(widget)();
    assert.equal(widget.onPointerDown, undefined);
});
