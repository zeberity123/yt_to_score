import {WorkspaceAPI} from './api.js';
import {CropSelection, fitMedia} from './crop.js';
import './i18n.js';

const $ = id => document.getElementById(id);
const api = new WorkspaceAPI();
const video = $('video');
video.volume = Number($('volume').value)/100;
$('review-speed').replaceChildren(...Array.from($('speed').options, option => option.cloneNode(true)));
let state = null, selected = 0, tab = 'capture', requesting = false, uploading = false;
let listSignature = '', currentMedia = '', job = null, errorShown = '', editorIndex = 0;
let polling = false, initialized = false, titleDirty = false;
const downloaded = new Set();

function fail(error) { $('error-text').textContent = error.message || String(error); $('error').hidden = false; }
function listen(id, event, callback) { $(id).addEventListener(event, e => Promise.resolve().then(() => callback(e)).catch(fail)); }
function clock(seconds, decimal = false) {
  seconds = Math.max(0, Number(seconds) || 0);
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole/60)).padStart(2,'0')}:${String(whole%60).padStart(2,'0')}${decimal ? '.'+Math.floor((seconds%1)*10) : ''}`;
}
function cropArray(region) { return [region.left, region.top, region.right, region.bottom]; }
function fitVideo() { fitMedia($('video-stage'), $('video-fit'), video.videoWidth, video.videoHeight); }
function fitEditor() { fitMedia($('editor-stage'), $('editor-fit'), $('editor-image').naturalWidth, $('editor-image').naturalHeight); }
const crop = new CropSelection($('video-crop'), {
  moveInside: false,
  onStart: () => video.pause(),
  onEnd: value => command('region', {crop:value}).catch(fail),
});
const editorCrop = new CropSelection($('editor-crop'), {onChange: value => {
  ['left','top','right','bottom'].forEach((side,i) => $(`crop-${side}`).value = (value[i]*100).toFixed(1));
}});
new ResizeObserver(fitVideo).observe($('video-stage'));
new ResizeObserver(fitEditor).observe($('editor-stage'));

async function command(action, data = {}) {
  requesting = true;
  updateControls();
  try {
    await api.command(action, data);
    await refresh();
  } finally { requesting = false; updateControls(); }
}
async function refresh() {
  const next = await api.state();
  const previous = state;
  state = next;
  if (next.notation && next.notation !== previous?.notation) $('notation').value = next.notation;
  if (!initialized) { Object.keys(next.artifacts).forEach(key => downloaded.add(key)); initialized = true; }
  if (previous?.busy && !next.busy) {
    if (job === 'extract' && !next.error) { selected = 0; setReviewAudio(false); switchTab('review'); }
    job = null;
  }
  for (const [key, artifact] of Object.entries(next.artifacts)) {
    if (!downloaded.has(key)) { downloaded.add(key); api.download(key, artifact.name); }
  }
  render();
}
function switchTab(next) {
  tab = next;
  if (tab === 'review' && !$('review-audio').checked) video.pause();
  $('capture-screen').hidden = tab !== 'capture';
  $('review-screen').hidden = tab !== 'review';
  for (const name of ['capture','review']) {
    $(`${name}-tab`).classList.toggle('active', tab === name);
    $(`${name}-tab`).setAttribute('aria-selected', String(tab === name));
  }
  requestAnimationFrame(fitVideo);
}
function setReviewAudio(enabled) {
  $('keep-review-audio').checked = $('review-audio').checked = enabled;
  updateControls();
}
async function togglePlayback() {
  if (!state?.video || video.readyState < 2 || video.seeking) return;
  if (video.paused) {
    if (tab === 'review') setReviewAudio(true);
    await video.play();
  } else video.pause();
}
function imageUrl(index, kind = 'line') { return api.url('image', {index, kind, v:state.revision}); }
function render() {
  if (!state) return;
  const manual = state.mode === 'manual';
  document.body.classList.toggle('has-video', !!state.video);
  $('automatic').setAttribute('aria-pressed', String(!manual));
  $('manual').setAttribute('aria-pressed', String(manual));
  $('auto-controls').hidden = manual;
  $('manual-controls').hidden = !manual;
  $('video-empty').hidden = !!state.video;
  $('video-fit').hidden = !state.video;
  const mediaKey = state.video ? state.videoId : '';
  if (mediaKey !== currentMedia) {
    currentMedia = mediaKey;
    if (state.video) { setReviewAudio(true); video.src = api.url('video', {v:state.revision}); video.load(); }
    else { video.pause(); video.removeAttribute('src'); video.load(); }
  }
  if (!crop.drag) crop.set(cropArray(state.region));
  $('duration').textContent = clock(state.duration);
  $('audio-note').hidden = !state.video || state.hasAudio !== false;
  $('seek').max = Math.max(0.01, state.duration-.01);
  if (!titleDirty && document.activeElement !== $('pdf-title')) $('pdf-title').value = state.title;
  $('source-note').textContent = state.source || 'YouTube · MP4 · MOV · MKV · WebM · AVI';
  $('tab-count').textContent = state.lines.length;
  $('line-count').textContent = state.lines.length;
  $('manual-count').textContent = state.lines.length;
  $('included-count').textContent = state.lines.length ? `${state.lines.filter(l => l.included).length} included · in export order` : 'Capture a line to get started.';
  selected = Math.max(0, Math.min(selected, state.lines.length-1));
  const signature = `${state.projectId}:${state.mode}:${JSON.stringify(state.lines)}`;
  if (signature !== listSignature) { listSignature = signature; renderLines(); }
  renderSelection();
  $('warning-list').replaceChildren(...state.warnings.map(text => { const li = document.createElement('li'); li.textContent = text; return li; }));
  $('warnings').hidden = !state.warnings.length;
  if (!uploading) $('status').textContent = state.status;
  $('progress').hidden = !state.busy;
  $('progress').value = state.progress;
  $('cancel').hidden = !state.busy;
  $('status-dot').classList.toggle('busy', state.busy || uploading);
  if (state.error && state.error !== errorShown) { errorShown = state.error; fail(state.error); }
  if (!state.error) errorShown = '';
  updateControls();
}
function renderLines() {
  $('line-list').replaceChildren(...state.lines.map((line,index) => {
    const button = document.createElement('button');
    button.className = `line-item${line.included ? '' : ' excluded'}`;
    button.setAttribute('aria-label', `Line ${index+1}, ${line.included ? 'included' : 'excluded'}`);
    const head = document.createElement('span'); head.className = 'line-item-head';
    const title = document.createElement('span'); title.textContent = `LINE ${String(index+1).padStart(2,'0')}`;
    const tick = document.createElement('span'); tick.textContent = line.included ? '✓' : '—'; head.append(title,tick);
    const img = document.createElement('img'); img.src = imageUrl(index); img.alt = ''; img.loading = 'lazy';
    const note = document.createElement('small'); note.textContent = `${clock(line.time,true)} · ${line.view ? 'Automatic capture' : 'Manual capture'}`;
    button.append(head,img,note);
    button.addEventListener('click', () => { selected = index; renderSelection(); updateControls(); });
    return button;
  }));
}
function renderSelection() {
  const line = state?.lines[selected];
  Array.from($('line-list').children).forEach((button,i) => button.setAttribute('aria-pressed', String(i===selected)));
  $('line-empty').hidden = !!line;
  $('line-image').hidden = !line;
  $('preview-title').textContent = line ? `Line ${String(selected+1).padStart(2,'0')}` : 'Line preview';
  if (line) {
    const key = `${state.projectId}:${state.mode}:${selected}:${line.path}`;
    if ($('line-image').dataset.key !== key) { $('line-image').src = imageUrl(selected); $('line-image').dataset.key = key; }
    $('include-line').textContent = 'Exclude line';
    $('line-meta').textContent = `${clock(line.time,true)} · ${line.included ? 'Included in PDF' : 'Excluded from PDF'}`;
  }
}
function updateControls() {
  const locked = !state || state.busy || requesting || uploading;
  const loaded = !!state?.video;
  const line = state?.lines[selected];
  const ready = loaded && video.readyState >= 2 && !video.seeking;
  const conditions = {
    'load-video':!!$('source').value.trim(), 'choose-video':true, 'open-project':true,
    automatic:true, manual:true, detect:ready, extract:loaded, play:ready,
    'add-line':ready, speed:loaded, mute:loaded && state.hasAudio !== false, volume:loaded && state.hasAudio !== false,
    'keep-review-audio':loaded && state.hasAudio !== false, 'review-audio':loaded && state.hasAudio !== false,
    'review-play':ready && state.hasAudio !== false && $('review-audio').checked,
    'review-speed':loaded && state.hasAudio !== false && $('review-audio').checked,
    'edit-line':!!line, 'include-line':!!line, 'move-up':!!line && selected>0,
    'undo-line':!!state?.canUndo,
    'move-down':!!line && selected<state.lines.length-1,
    'save-project':!!state?.lines.length, 'export-pdf':!!state?.lines.some(l => l.included),
    'for-print':true, notation:true,
  };
  for (const [id, enabled] of Object.entries(conditions)) $(id).disabled = locked || !enabled;
  $('seek').disabled = locked || !loaded;
  crop.enabled = !locked && ready;
  $('pdf-title').disabled = locked;
}
async function choose(kind) {
  if (window.desktop) {
    const path = await api.choose(kind);
    if (!path) return;
    if (kind === 'video') { $('source').value = path; updateControls(); }
    else { video.pause(); titleDirty = false; await command('open', {path}); selected = 0; switchTab('review'); }
  } else $(kind === 'video' ? 'video-file' : 'project-file').click();
}
async function upload(file, kind) {
  if (!file) return;
  uploading = true; updateControls();
  try {
    const path = await api.upload(file, fraction => $('status').textContent = `Importing ${file.name} · ${Math.round(fraction*100)}%`);
    if (kind === 'video') { $('source').value = path; await loadVideo(); }
    else { video.pause(); titleDirty = false; await command('open', {path}); switchTab('review'); }
  } finally { uploading = false; updateControls(); }
}
async function loadVideo() {
  video.pause(); job = 'load'; titleDirty = false;
  await command('load', {source:$('source').value, layout:$('layout').value, notation:$('notation').value});
}
listen('capture-tab','click', () => switchTab('capture'));
listen('review-tab','click', () => switchTab('review'));
listen('review-lines','click', () => switchTab('review'));
listen('back-capture','click', () => switchTab('capture'));
listen('dismiss-error','click', () => $('error').hidden = true);
listen('source','input', updateControls);
listen('source','keydown', e => { if (e.key === 'Enter' && !$('load-video').disabled) return loadVideo(); });
listen('choose-video','click', () => choose('video'));
listen('open-project','click', () => choose('project'));
listen('video-file','change', e => upload(e.target.files[0], 'video'));
listen('project-file','change', e => upload(e.target.files[0], 'project'));
listen('load-video','click', loadVideo);
for (const mode of ['automatic','manual']) listen(mode,'click', async () => {
  video.pause(); selected = 0;
  await command('mode', {mode});
  if (mode === 'manual') setReviewAudio(true);
  if (mode === 'manual' && !state.lines.length && state.video) video.currentTime = 0;
});
listen('detect','click', () => { video.pause(); return command('detect', {time:video.currentTime, layout:$('layout').value, notation:$('notation').value}); });
listen('notation','change', () => { if (state?.video) { video.pause(); return command('detect', {time:video.currentTime, layout:$('layout').value, notation:$('notation').value}); } });
listen('extract','click', async () => {
  video.pause(); setReviewAudio(false); job = 'extract';
  await command('extract', {interval:$('interval').value, threshold:$('threshold').value, start:$('start').value,
    end:$('end').value, overlap:true, notation:$('notation').value});
});
listen('cancel','click', () => command('cancel'));
listen('play','click', togglePlayback);
listen('review-play','click', togglePlayback);
for (const id of ['speed','review-speed']) listen(id,'change', () => {
  const value = $(id).value;
  $('speed').value = $('review-speed').value = value;
  video.playbackRate = Number(value);
});
for (const id of ['keep-review-audio','review-audio']) listen(id,'change', async () => {
  const enabled = $(id).checked;
  setReviewAudio(enabled);
  if (tab === 'review') {
    if (enabled) await video.play();
    else video.pause();
  }
});
listen('mute','click', () => {
  if (video.muted || video.volume === 0) {
    video.muted = false;
    if (video.volume === 0) video.volume = .7;
  } else video.muted = true;
});
listen('volume','input', () => { video.volume = Number($('volume').value)/100; video.muted = false; });
video.addEventListener('volumechange', () => {
  const muted = video.muted || video.volume === 0;
  $('mute').textContent = muted ? 'Unmute' : 'Mute';
  $('mute').setAttribute('aria-label', muted ? 'Unmute audio' : 'Mute audio');
  $('mute').setAttribute('aria-pressed', String(muted));
  $('volume').value = Math.round(video.volume*100);
  $('volume-value').textContent = video.muted ? 'Muted' : `${Math.round(video.volume*100)}%`;
});
listen('add-line','click', async () => { selected = state.lines.length; await command('capture', {time:video.currentTime}); });
listen('seek','input', () => { video.pause(); video.currentTime = Number($('seek').value); $('current-time').textContent = clock(video.currentTime,true); });
video.addEventListener('timeupdate', () => { $('seek').value = video.currentTime; $('current-time').textContent = clock(video.currentTime,true); });
video.addEventListener('loadedmetadata', () => { video.playbackRate = Number($('speed').value); video.currentTime = state.mode === 'manual' ? 0 : Math.min(20, state.duration*.1); fitVideo(); });
for (const event of ['loadeddata','seeked','seeking','play','pause','ended']) video.addEventListener(event, () => { $('play').textContent = $('review-play').textContent = video.paused ? '▶ Play' : 'Ⅱ Pause'; updateControls(); });
video.addEventListener('error', () => { if (video.getAttribute('src')) fail('This video could not be played. Reload it or try an H.264 MP4 file.'); });
listen('pdf-title','input', () => { titleDirty = true; });
listen('for-print','click', () => {
  $('gap').value = '0';
  $('left-margin').value = $('right-margin').value = '12';
});
listen('include-line','click', () => command('remove', {index:selected}));
listen('undo-line','click', async () => {
  selected = state.undoIndex;
  await command('undo');
});
for (const [id,direction] of [['move-up',-1],['move-down',1]]) listen(id,'click', async () => {
  const index = selected; selected += direction;
  try { await command('move', {index,direction}); } catch (error) { selected = index; throw error; }
});
listen('save-project','click', () => { video.pause(); job = 'save'; return command('save', {title:$('pdf-title').value}); });
listen('export-pdf','click', () => { video.pause(); job = 'export'; return command('export', {title:$('pdf-title').value, paper:$('paper').value,
  gap:$('gap').value, left:$('left-margin').value, right:$('right-margin').value}); });
listen('edit-line','click', () => {
  editorIndex = selected;
  const line = state.lines[selected];
  $('editor-title').textContent = `Edit line ${String(selected+1).padStart(2,'0')}`;
  $('editor-hint').textContent = line.source_path ? 'Drag the corners to crop or expand into the original frame. Drag inside to move the selection.' : 'This older project contains only the captured image. Crop it here; expansion is limited to its original edges.';
  $('editor-image').src = imageUrl(selected,'source');
  editorCrop.set(line.crop || [0,0,1,1]);
  $('editor').showModal();
  requestAnimationFrame(fitEditor);
});
$('editor-image').addEventListener('load', fitEditor);
for (const id of ['close-editor','cancel-edit']) listen(id,'click', () => $('editor').close());
for (const side of ['left','top','right','bottom']) listen(`crop-${side}`,'change', () => {
  const value = ['left','top','right','bottom'].map(s => Number($(`crop-${s}`).value)/100);
  if (value.every(Number.isFinite) && value[0]>=0 && value[1]>=0 && value[2]<=1 && value[3]<=1 && value[2]>value[0] && value[3]>value[1]) editorCrop.set(value);
  else { editorCrop.set(editorCrop.value); throw new Error('Crop edges must form a rectangle within 0–100%.'); }
});
listen('apply-edit','click', async () => {
  $('apply-edit').disabled = true;
  try { await command('edit', {index:editorIndex,crop:editorCrop.value}); $('editor').close(); }
  finally { $('apply-edit').disabled = false; }
});
listen('reset-line','click', async () => { await command('edit', {index:editorIndex,reset:true}); $('editor').close(); });
document.addEventListener('keydown', e => {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  // Keep spaces available for titles/URLs, but never activate a focused action button.
  if (e.code === 'Space' && !e.target.closest('textarea,[contenteditable]:not([contenteditable="false"]),input:not([type=range],[type=checkbox],[type=number])')) {
    e.preventDefault();
    if (!e.repeat) togglePlayback().catch(fail);
    return;
  }
  if (
      e.target.closest('input,select,textarea,[contenteditable]:not([contenteditable="false"])') ||
      $('editor').open || state?.busy || requesting || uploading) return;
  const direction = {ArrowUp:-1, ArrowLeft:-1, ArrowDown:1, ArrowRight:1}[e.key];
  if (tab === 'review' && direction && state?.lines.length) {
    e.preventDefault();
    selected = Math.max(0, Math.min(selected + direction, state.lines.length - 1));
    renderSelection();
    updateControls();
    const button = $('line-list').children[selected];
    button.focus({preventScroll:true});
    button.scrollIntoView({block:'nearest',inline:'nearest'});
    return;
  }
});
async function poll() {
  if (!polling && !requesting && !$('editor').open) {
    polling = true;
    try { await refresh(); } catch (error) { $('status').textContent = 'Connection lost. Reopen the app to reconnect.'; if (!initialized) fail(error); }
    finally { polling = false; }
  }
  setTimeout(poll, state?.busy ? 350 : 900);
}
updateControls();
poll();
