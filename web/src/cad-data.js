/** Validate the complete offline CAD document before allocating any GPU buffers. */
export function validateCAD(source) {
  if (!Array.isArray(source) || !source.length || source.length > 128) throw new Error('Invalid CAD part count');
  const names = new Set(); let triangles = 0, vertices = 0;
  const finiteVector = (v, n, limit) => Array.isArray(v) && v.length === n && v.every(x => Number.isFinite(x) && Math.abs(x) <= limit);
  for (const part of source) {
    if (!part || typeof part.name !== 'string' || !/^[A-Za-z0-9_-]{1,96}$/.test(part.name) || names.has(part.name)) throw new Error('Invalid or duplicate CAD part name');
    names.add(part.name);
    if (!finiteVector(part.color,3,1) || part.color.some(x=>x<0) || !Number.isFinite(part.opacity) || part.opacity<0 || part.opacity>1 || !finiteVector(part.explode,3,2000)) throw new Error('Invalid CAD appearance');
    if (!Array.isArray(part.vertices) || !Array.isArray(part.triangles) || !part.vertices.length || !part.triangles.length) throw new Error('Missing CAD geometry');
    vertices += part.vertices.length; triangles += part.triangles.length;
    if (vertices>600_000 || triangles>600_000) throw new Error('CAD geometry exceeds memory budget');
    if (!part.vertices.every(v=>finiteVector(v,3,2000))) throw new Error('Invalid CAD coordinate');
    for (const ids of part.triangles) if (!Array.isArray(ids) || ids.length!==3 || !ids.every(i=>Number.isInteger(i)&&i>=0&&i<part.vertices.length)) throw new Error('Invalid CAD triangle index');
  }
  return source;
}

/** Flat face normals require expansion, but no per-triangle JS arrays/GC churn. */
export function packCAD(part) {
  const data = new Float32Array(part.triangles.length*18); let offset = 0;
  for (const [ia,ib,ic] of part.triangles) {
    const a=part.vertices[ia],b=part.vertices[ib],c=part.vertices[ic];
    // Convert mm/Z-up to renderer units/Y-up; reflection changes handedness.
    const abx=b[0]-a[0],aby=b[2]-a[2],abz=b[1]-a[1];
    const acx=c[0]-a[0],acy=c[2]-a[2],acz=c[1]-a[1];
    const nx=acy*abz-acz*aby,ny=acz*abx-acx*abz,nz=acx*aby-acy*abx;
    const length=Math.hypot(nx,ny,nz)||1;
    for (const v of [a,b,c]) {
      data[offset++]=v[0]/60; data[offset++]=v[2]/60; data[offset++]=v[1]/60;
      data[offset++]=nx/length; data[offset++]=ny/length; data[offset++]=nz/length;
    }
  }
  return data;
}
