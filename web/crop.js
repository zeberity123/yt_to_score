const clamp = (n, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, n));

export class CropSelection {
  constructor(element, {onChange = () => {}, onStart = () => {}, onEnd = () => {}, moveInside = true} = {}) {
    this.element = element;
    this.box = element.querySelector('.crop-box');
    this.value = [0, 0, 1, 1];
    this.enabled = true;
    this.moveInside = moveInside;
    this.callbacks = {onChange, onStart, onEnd};
    element.addEventListener('pointerdown', e => this.start(e));
    element.addEventListener('pointermove', e => this.move(e));
    element.addEventListener('pointerup', e => this.end(e));
    element.addEventListener('pointercancel', () => { if (this.drag) this.set(this.drag.original); this.drag = null; });
  }
  set(value) {
    this.value = value.slice();
    const [l,t,r,b] = value;
    Object.assign(this.box.style, {left:`${l*100}%`, top:`${t*100}%`, width:`${(r-l)*100}%`, height:`${(b-t)*100}%`});
    this.callbacks.onChange(this.value);
  }
  point(e) {
    const r = this.element.getBoundingClientRect();
    return [clamp((e.clientX-r.left)/r.width), clamp((e.clientY-r.top)/r.height)];
  }
  start(e) {
    if (!this.enabled || e.button !== 0) return;
    e.preventDefault();
    this.element.setPointerCapture(e.pointerId);
    this.callbacks.onStart();
    this.drag = {origin:this.point(e), original:this.value.slice(), handle:e.target.dataset.handle || (this.moveInside && e.target.closest('.crop-box') ? 'move' : 'new')};
  }
  move(e) {
    if (!this.drag) return;
    const [x,y] = this.point(e), d = this.drag, [ox,oy] = d.origin;
    let [l,t,r,b] = d.original;
    if (d.handle === 'new') [l,t,r,b] = [Math.min(x,ox),Math.min(y,oy),Math.max(x,ox),Math.max(y,oy)];
    else if (d.handle === 'move') {
      const dx = clamp(x-ox, -l, 1-r), dy = clamp(y-oy, -t, 1-b);
      [l,t,r,b] = [l+dx,t+dy,r+dx,b+dy];
    } else {
      if (d.handle.includes('w')) l = Math.min(x,r-.002);
      if (d.handle.includes('e')) r = Math.max(x,l+.002);
      if (d.handle.includes('n')) t = Math.min(y,b-.002);
      if (d.handle.includes('s')) b = Math.max(y,t+.002);
    }
    if (r-l >= .002 && b-t >= .002) this.set([l,t,r,b]);
  }
  end(e) {
    if (!this.drag) return;
    this.move(e);
    this.drag = null;
    this.callbacks.onEnd(this.value);
  }
}

export function fitMedia(stage, container, width, height) {
  if (!(width > 0 && height > 0)) return;
  const ratio = Math.min(stage.clientWidth/width, stage.clientHeight/height);
  container.style.width = `${Math.floor(width*ratio)}px`;
  container.style.height = `${Math.floor(height*ratio)}px`;
}
