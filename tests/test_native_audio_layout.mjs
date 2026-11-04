import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installNativeAudioLayout } from '../web/native_audio_layout.js';

function fixture(vue = true) {
    const frames = new Map(), observers = [], listeners = new Map();
    let id = 0;
    class Observer {
        constructor(callback) { this.callback = callback; this.targets = []; observers.push(this); }
        observe(target) { this.targets.push(target); }
        disconnect() { this.targets = []; }
    }
    const env = {
        requestAnimationFrame(fn) { frames.set(++id, fn); return id; },
        cancelAnimationFrame(key) { frames.delete(key); },
        ResizeObserver: Observer, MutationObserver: Observer,
    };
    const row = { clientWidth: 440, style: {} };
    const content = { clientWidth: 416, style: {} };
    const host = { clientWidth: 40, parentElement: content, style: {}, closest: () => vue ? row : null };
    const audio = {
        isConnected: true, parentElement: host, style: {},
        getBoundingClientRect() { throw Error('Zoomed screen coordinates must not size the player'); },
        addEventListener(name, callback) { listeners.set(name, callback); },
        removeEventListener(name) { listeners.delete(name); },
    };
    const widget = { element: audio, margin: 10, options: {} };
    const node = { size: [440, 340] };
    const layout = installNativeAudioLayout(node, widget, env);
    const flush = () => { const current = [...frames.values()]; frames.clear(); current.forEach(fn => fn()); };
    return { env, row, content, host, audio, widget, node, layout, frames, observers, listeners, flush };
}

test('repairs a clipped Vue host and uses the full logical content width', () => {
    const f = fixture();
    assert.equal(f.host.style.width, '100%');
    assert.equal(f.host.style.minWidth, '0px');
    assert.equal(f.host.style.contain, 'inline-size');
    assert.equal(f.audio.style.width, '416px');
    f.layout.dispose();
});

test('recovers after metadata, repeated narrow measurements, and node resizing', () => {
    const f = fixture();
    for (let i = 0; i < 100; i++) {
        f.audio.style.width = '40px';
        f.host.clientWidth = 40;
        f.listeners.get('loadedmetadata')();
        f.flush();
        assert.equal(f.audio.style.width, '416px');
    }
    f.content.clientWidth = 550;
    f.node.size[0] = 574;
    f.widget.options.afterResize();
    assert.equal(f.audio.style.width, '550px');
    f.layout.dispose();
});

test('rebinds observers when the element is reparented and ignores graph zoom', () => {
    const f = fixture();
    const nextHost = { clientWidth: 30, parentElement: { clientWidth: 500 }, style: {}, closest: () => f.row };
    f.audio.parentElement = nextHost;
    f.node.size[0] = 524;
    f.layout.refresh();
    assert.equal(f.audio.style.width, '500px');
    assert.equal(nextHost.style.width, '100%');
    assert.ok(f.observers.some(observer => observer.targets.includes(nextHost)));
    assert.ok(!f.observers.some(observer => observer.targets.includes(f.host)));
    f.layout.dispose();
});

test('classic renderer respects its allocated clipping host', () => {
    const f = fixture(false);
    assert.equal(f.audio.style.width, '40px');
    assert.equal(f.host.style.width, undefined);
    f.layout.dispose();
});

test('coalesces resize notifications and removes all hooks on disposal', () => {
    const f = fixture();
    for (const observer of f.observers) for (let i = 0; i < 20; i++) observer.callback();
    assert.equal(f.frames.size, 1);
    f.layout.dispose();
    assert.equal(f.frames.size, 0);
    assert.equal(f.listeners.size, 0);
    assert.ok(f.observers.every(observer => observer.targets.length === 0));
    assert.equal(f.widget.options.afterResize, undefined);
    f.audio.style.width = '30px';
    f.layout.refresh();
    f.flush();
    assert.equal(f.audio.style.width, '30px');
});


test('stale or oversized host measurements cannot grow beyond the independent node width', () => {
    const f = fixture();
    f.host.clientWidth = 900;
    for (let i = 0; i < 100; i++) {
        f.content.clientWidth = 900 + i * 10;
        f.layout.refresh();
        assert.equal(f.audio.style.width, '420px');
        assert.equal(f.audio.style.maxWidth, '100%');
    }
    f.node.size[0] = 240;
    f.content.clientWidth = 216;
    f.layout.refresh();
    assert.equal(f.audio.style.width, '216px');
    assert.equal(f.audio.style.minWidth, '0px');
    f.layout.dispose();
});

test('parent padding is excluded instead of increasing the border-box audio width', () => {
    const f = fixture();
    f.env.getComputedStyle = () => ({paddingLeft:'12px',paddingRight:'12px'});
    f.layout.refresh();
    assert.equal(f.audio.style.width, '392px');
    f.layout.dispose();
});
