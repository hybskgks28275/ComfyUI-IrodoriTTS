import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
const src = readFileSync(new URL('../web/i18n.js', import.meta.url), 'utf8');
function setup() {
    let value;
    const settings = new EventTarget();
    settings.getSettingValue = () => value;
    const api = new Function('app', src.replace(/^import .*;\r?\n/m, '').replaceAll('export ', '') + '\nreturn {t,locale,watchLocale};')({ui:{settings}});
    return {...api, change(next) { value=next; settings.dispatchEvent(new Event('Comfy.Locale.change')); }};
}
test('Japanese is opt-in; unknown and unset locales use English', () => {
    const api=setup();
    for (const lang of [undefined, null, '', 'en', 'zh', 'fr', 'javanese']) {
        api.change(lang); assert.equal(api.t('English', '日本語'), 'English');
    }
    for (const lang of ['ja', 'ja-JP', 'ja_JP']) {
        api.change(lang); assert.equal(api.t('English', '日本語'), '日本語');
    }
});
test('existing widgets refresh on locale change and unsubscribe on removal', () => {
    const api=setup(); let text, refreshes=0, removed=0;
    const node={onRemoved(){removed++;return 'removed';}};
    api.watchLocale(node,()=>{text=api.t('English','日本語');refreshes++;});
    assert.equal(text,'English'); api.change('ja'); assert.equal(text,'日本語');
    api.change('en'); assert.equal(text,'English');
    assert.equal(node.onRemoved(),'removed'); api.change('ja');
    assert.equal(refreshes,3); assert.equal(removed,1);
});
test('English and Japanese definitions have matching node and slot keys', () => {
    const read=lang=>JSON.parse(readFileSync(new URL(`../locales/${lang}/nodeDefs.json`,import.meta.url),'utf8'));
    const en=read('en'), ja=read('ja'); assert.deepEqual(Object.keys(en),Object.keys(ja));
    assert.equal(Object.keys(en).length,3);
    assert.doesNotMatch(JSON.stringify(en),/[ぁ-んァ-ヶ一-龠]/u);
    for (const name of Object.keys(en)) {
        for (const slots of ['inputs','outputs']) {
            assert.deepEqual(Object.keys(en[name][slots]),Object.keys(ja[name][slots]));
        }
    }
});
test('all 45 emoji tokens retain English and Japanese descriptions', async () => {
    const source=readFileSync(new URL('../web/emoji_data.js',import.meta.url),'utf8');
    const {EMOJIS}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
    assert.equal(EMOJIS.length,45); assert.equal(new Set(EMOJIS.map(e=>e[0])).size,45);
    for (const [emoji,en,description,ja,jaDescription] of EMOJIS) {
        assert.ok(emoji&&en&&description&&ja&&jaDescription);
        assert.doesNotMatch(en+description,/[ぁ-んァ-ヶ一-龠]/u);
    }
});
