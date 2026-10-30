import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import { installNativeAudioLayout } from '../web/native_audio_layout.js';

const source = readFileSync(new URL('../web/save_audio_preview.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '');

function fixture() {
    let extension;
    const elements = [];
    const document = {
        createElement(tag) {
            const attributes = new Map();
            const element = {
                tagName: tag.toUpperCase(), style: {}, listeners: {}, pauses: 0, loads: 0,
                setAttribute(k, v) { attributes.set(k, v); },
                getAttribute(k) { return attributes.get(k) ?? null; },
                removeAttribute(k) { attributes.delete(k); },
                addEventListener(k, fn) { this.listeners[k] = fn; },
                removeEventListener(k) { delete this.listeners[k]; },
                pause() { this.pauses++; }, load() { this.loads++; },
                set src(v) { attributes.set('src', v); }, get src() { return attributes.get('src'); },
            };
            elements.push(element);
            return element;
        },
    };
    vm.runInNewContext(source, {
        installNativeAudioLayout,
        app: { registerExtension(value) { extension = value; } },
        api: { apiURL: value => value }, document, URL, URLSearchParams,
        window: { location: { href: 'http://localhost:8188/' } },
        t: english => english, locale: () => 'en', watchLocale: (_, update) => update(),
    });
    class Node {
        widgets = [];
        addDOMWidget(name, type, element, options) {
            const widget = { name, type, element, options,
                computeLayoutSize: () => ({ minWidth: 0, minHeight: 50 }) };
            Object.defineProperty(widget, 'value', { get: options.getValue, set: options.setValue });
            this.widgets.push(widget);
            return widget;
        }
    }
    extension.beforeRegisterNodeDef(Node, { name: 'IrodoriTTSSaveAudio' });
    const node = new Node(); node.onNodeCreated();
    return { node, widget: node.widgets[0], audio: elements[0], elements };
}

test('native player is the DOM root with responsive CSS and layout bounds', () => {
    const { widget, audio, elements } = fixture();
    assert.equal(elements.length, 1);
    assert.equal(widget.element, audio);
    assert.equal(audio.tagName, 'AUDIO');
    assert.equal(audio.controls, true);
    assert.match(audio.style.cssText, /min-width:0/);
    assert.match(audio.style.cssText, /max-width:100%/);
    assert.equal(widget.computeLayoutSize().minWidth, 300);
    assert.equal(widget.computeLayoutSize().minHeight, 66);
    assert.equal(widget.computeLayoutSize().maxHeight, 66);
    assert.equal(widget.serialize, false);
});

test('repeated executions retain one player and load each new saved file once', () => {
    const { node, widget, audio, elements } = fixture();
    audio.volume = .4;
    for (let i = 0; i < 100; i++) {
        node.onExecuted({ audio: [{ filename: `${i}.wav`, subfolder: 'audio/test' }] });
        const loads = audio.loads;
        widget.value = `/view?type=output&filename=${i}.wav&subfolder=audio%2Ftest&rand=${i}`;
        assert.equal(audio.loads, loads);
    }
    assert.equal(audio.loads, 100);
    assert.equal(elements.length, 1);
    assert.equal(audio.volume, .4);
});

test('core output restoration does not cause another load in onExecuted', () => {
    const { node, widget, audio } = fixture();
    for (let i = 0; i < 30; i++) {
        const url = `/view?filename=${i}.flac&subfolder=audio&type=output&rand=${i}`;
        widget.element.src = url;
        widget.value = url;
        node.onExecuted({ audio: [{ filename: `${i}.flac`, subfolder: 'audio' }] });
    }
    assert.equal(audio.loads, 0);
    assert.match(audio.src, /29\.flac/);
    node.onRemoved();
    assert.equal(audio.getAttribute('src'), null);
    assert.equal(audio.loads, 1);
});

test('non-view sources and different subfolders remain distinct; native controls keep events', () => {
    const { node, widget, audio } = fixture();
    widget.value = 'blob:first'; widget.value = 'blob:second';
    assert.equal(audio.loads, 2);
    node.onExecuted({ audio: [{ filename: 'same.wav', subfolder: 'a' }] });
    node.onExecuted({ audio: [{ filename: 'same.wav', subfolder: 'b' }] });
    assert.equal(audio.loads, 4);
    let stopped = 0;
    audio.listeners.pointerdown({ stopPropagation() { stopped++; } });
    audio.listeners.keydown({ stopPropagation() { stopped++; } });
    assert.equal(stopped, 2);
});
