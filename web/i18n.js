// English is the source language; placeholders preserve filenames, counts and times.
const catalog = await (await fetch('./locales.json')).json();
const supported = ['en', 'ko', 'ja'];
let language = await window.desktop?.getLanguage() || localStorage.getItem('language') || 'en';
if (!supported.includes(language)) language = 'en';
const originals = new WeakMap();
const attributes = new WeakMap();
const patterns = Object.entries(catalog).filter(([key]) => key.includes('{'))
  .sort(([a],[b]) => b.replace(/\{\w+\}/g,'').length - a.replace(/\{\w+\}/g,'').length).map(([key, values]) => {
  const names = [];
  const pattern = key.split(/(\{\w+\})/).map(part => {
    if (/^\{\w+\}$/.test(part)) { names.push(part.slice(1,-1)); return '(.+?)'; }
    return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }).join('');
  return {regex:new RegExp(`^${pattern}$`), names, values};
});
export function translate(source) {
  if (language === 'en') return source;
  const index = language === 'ko' ? 0 : 1;
  if (catalog[source]) return catalog[source][index];
  for (const {regex, names, values} of patterns) {
    const match = source.match(regex);
    if (match) return values[index].replace(/\{(\w+)\}/g, (_, name) => match[names.indexOf(name)+1]);
  }
  return source;
}
function localize(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.parentElement?.closest('script,style,#language,#source-note')) continue;
    const previous = originals.get(node);
    const source = previous && node.data === previous.output ? previous.source : node.data;
    const output = source.replace(/\S[\s\S]*\S|\S/, text => translate(text));
    originals.set(node, {source, output});
    if (node.data !== output) node.data = output;
  }
  for (const element of root.querySelectorAll('[title],[aria-label],[placeholder],[alt]')) {
    let saved = attributes.get(element);
    if (!saved) { saved = {}; attributes.set(element, saved); }
    for (const name of ['title','aria-label','placeholder','alt']) {
      const value = element.getAttribute(name);
      if (!value) continue;
      const previous = saved[name];
      const source = previous && value === previous.output ? previous.source : value;
      const output = translate(source);
      saved[name] = {source, output};
      if (value !== output) element.setAttribute(name, output);
    }
  }
}
const observer = new MutationObserver(apply);
function apply() {
  observer.disconnect();
  document.documentElement.lang = language;
  localize(document.body);
  observer.observe(document.body, {childList:true, subtree:true, characterData:true, attributes:true,
    attributeFilter:['title','aria-label','placeholder','alt']});
}
const select = document.getElementById('language');
select.value = language;
select.addEventListener('change', async () => {
  language = select.value;
  localStorage.setItem('language', language);
  apply();
  try { await window.desktop?.setLanguage(language); }
  catch (error) { document.getElementById('error-text').textContent = translate('Could not save the language preference.'); document.getElementById('error').hidden = false; }
});
apply();
