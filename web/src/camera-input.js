import {clamp} from './math.js';

/** At most two pointer captures; listeners and captures share one explicit lifetime. */
export function attachCameraInput(canvas, params, reset) {
  const controller = new AbortController(), points = new Map();
  const listen = (type, fn, options = {}) => canvas.addEventListener(type, fn, {...options, signal: controller.signal});
  const distance = () => { const [a, b] = [...points.values()]; return a && b ? Math.hypot(a.x-b.x, a.y-b.y) : 0; };
  let span = 0;
  listen('pointerdown', e => {
    if (e.button !== 0 || points.size >= 2) return;
    e.preventDefault();
    try { canvas.setPointerCapture(e.pointerId); } catch { return; }
    points.set(e.pointerId, {x:e.clientX, y:e.clientY}); span = distance();
    canvas.focus({preventScroll:true});
  });
  listen('pointermove', e => {
    const previous = points.get(e.pointerId); if (!previous) return;
    points.set(e.pointerId, {x:e.clientX, y:e.clientY});
    if (points.size === 1) {
      params.yaw += (e.clientX-previous.x)*.007;
      params.pitch = clamp(params.pitch+(e.clientY-previous.y)*.0025,-.23,.72);
    } else {
      const next = distance();
      if (span > 2 && next > 2) params.zoom = clamp(params.zoom*span/next,.55,1.8);
      span = next;
    }
  });
  const end = e => {
    points.delete(e.pointerId); span = distance();
    if (canvas.hasPointerCapture?.(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
  };
  for (const type of ['pointerup','pointercancel','lostpointercapture']) listen(type, end);
  listen('wheel', e => {
    e.preventDefault();
    const units = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? canvas.clientHeight : 1;
    params.zoom = clamp(params.zoom*Math.exp(clamp(e.deltaY*units,-1000,1000)*.001),.55,1.8);
  }, {passive:false});
  listen('dblclick', reset);
  listen('keydown', e => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const step = e.shiftKey ? .2 : .05;
    switch (e.key) {
      case 'ArrowLeft': params.yaw -= step; break;
      case 'ArrowRight': params.yaw += step; break;
      case 'ArrowUp': params.pitch = clamp(params.pitch-step,-.23,.72); break;
      case 'ArrowDown': params.pitch = clamp(params.pitch+step,-.23,.72); break;
      case '+': case '=': params.zoom = clamp(params.zoom/1.1,.55,1.8); break;
      case '-': params.zoom = clamp(params.zoom*1.1,.55,1.8); break;
      case 'Home': reset(); break;
      default: return;
    }
    e.preventDefault();
  });
  return () => {
    controller.abort();
    for (const id of points.keys()) if (canvas.hasPointerCapture?.(id)) canvas.releasePointerCapture(id);
    points.clear();
  };
}
