import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';
const source = readFileSync(new URL('../web/emoji_palette.js', import.meta.url), 'utf8');
const reorder = new Function('paletteWidget', 'textWidget', source.slice(source.indexOf('            paletteWidget.serialize = false;'), source.indexOf('            toggle.addEventListener')));
const names = ['mode','text','seed','control_after_generate','steps','cfg_text','cfg_reference','cfg_caption','seconds','duration_scale','device','precision','codec_device','allow_download','caption','unload_after_generate','model_name','dynamic_vram'];
function node() {
    const values = ['text','',0,'fixed',40,3,5,3,0,1,'auto','fp32','cpu',true,'',false,'Irodori-TTS-v4.1-Small',true];
    const n = {
        widgets: names.map((name,i)=>({name,value:values[i]})),
        configure(info) { this.widgets.filter(w=>w.serialize!==false).forEach((w,i)=>{w.value=info.widgets_values[i]}); },
        serializeFromStoreState() { return { widgets_values:this.widgets.filter(w=>w.serialize!==false).map(w=>w.value) }; },
    };
    const palette = {name:'irodori_emoji_palette'};
    n.widgets.push(palette);
    reorder.call(n,palette,n.widgets[1]);
    return n;
}
test('all legacy samples restore and serialize in canonical order',()=>{
    for(const file of readdirSync(new URL('../examples/',import.meta.url)).filter(f=>f.endsWith('.json'))) {
        const data=JSON.parse(readFileSync(new URL(`../examples/${file}`,import.meta.url),'utf8'));
        const info=data.nodes.find(n=>n.type==='IrodoriTTSGenerate');
        const n=node(); n.configure(info);
        assert.deepEqual(n.serializeFromStoreState().widgets_values.slice(0,info.widgets_values.length),info.widgets_values,file);
        assert.deepEqual(n.widgets.slice(0,5).map(w=>w.name),['mode','text','irodori_emoji_palette','model_name','seed']);
        assert.equal(n.widgets.find(w=>w.name==='dynamic_vram').value,true);
    }
});
test('edited model and seed survive save/reload without changing input data',()=>{
    const n=node(); n.widgets.find(w=>w.name==='model_name').value='Irodori-TTS-v4-Large';
    n.widgets.find(w=>w.name==='seed').value=9988;
    const saved=n.serializeFromStoreState(), before=structuredClone(saved), restored=node(); restored.configure(saved);
    assert.deepEqual(saved,before);
    assert.deepEqual(restored.serializeFromStoreState(),saved);
    assert.equal(saved.widgets_values[16],'Irodori-TTS-v4-Large');
    assert.equal(saved.widgets_values[2],9988);
});
test('named workflow values restore independently of visual order',()=>{
    const n=node(); n.configure({widgets_values:[],widgets_values_named:{model_name:'Irodori-TTS-v4-Large',seed:42}});
    assert.equal(n.serializeFromStoreState().widgets_values[16],'Irodori-TTS-v4-Large');
    assert.equal(n.serializeFromStoreState().widgets_values[2],42);
});
