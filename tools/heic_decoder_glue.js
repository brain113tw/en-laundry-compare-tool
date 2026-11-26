'use strict';
// Glue script of vendor/heic-decoder.html. Edit here, then run: node tools/build_heic_decoder.mjs <path to libheif-bundle.js>
//
// The page is loaded by index.html in a frame with sandbox="allow-scripts": it has an opaque origin, so it cannot reach the
// embedding page, its storage or its files, and its own policy (default-src 'none') leaves it no network. All it can do is
// receive the bytes of one HEIC file and answer with pixels.
//
// Messages, the whole interface between the tool and this page:
//   to this page     {type: 'decode', id, buffer, maxPixels, maxCoded}
//                    buffer: the bytes of one file; maxPixels: a larger picture is refused before it is decoded;
//                    maxCoded: the largest coded picture inside the file (a tile, for instance) the library may decode
//   from this page   {type: 'ready'}                             once, when the decoder has started
//                    {type: 'result', id, ok: true, width, height, opaque, colour, buffer}     buffer: RGBA pixels, already sRGB
//                    {type: 'result', id, ok: false, message}
//                    {type: 'fatal', message}                    the decoder cannot continue
//   colour is 'p3' when the file was Display P3 (converted here), 'other' for a colour space left as it is, '' otherwise.
//
// libheif itself runs in a worker built from the text block above, so decoding a large photo does not freeze anything.
(() => {
  const source = document.getElementById('libheif').textContent + '\n;(' + workerMain.toString() + ')();';
  const worker = new Worker(URL.createObjectURL(new Blob([source], {type: 'text/javascript'})));
  worker.onmessage = e => { const m = e.data; parent.postMessage(m, '*', m && m.buffer instanceof ArrayBuffer ? [m.buffer] : []); };
  worker.onerror = e => { parent.postMessage({type: 'fatal', message: String(e && e.message || 'decoder worker failed')}, '*'); };
  addEventListener('message', e => {
    const m = e.data;
    if (e.source !== parent || !m || m.type !== 'decode' || !(m.buffer instanceof ArrayBuffer)) return;
    worker.postMessage({id: m.id, buffer: m.buffer, maxPixels: m.maxPixels, maxCoded: m.maxCoded}, [m.buffer]);
  });
})();

// Everything below runs inside the worker (its source text is appended to the library text).
function workerMain() {
  let lib = null;
  try { lib = libheif(); postMessage({type: 'ready'}); } catch (e) { postMessage({type: 'fatal', message: String(e && e.message || e)}); return; }
  const failed = (id, err) => postMessage({type: 'result', id, ok: false, message: String(err && err.message || err)});
  // The library decodes inside its own timer callback; a trap there would otherwise leave the caller waiting.
  addEventListener('unhandledrejection', e => { postMessage({type: 'fatal', message: String(e.reason && e.reason.message || e.reason || 'decoder failed')}); });

  onmessage = e => {
    const {id, buffer} = e.data, maxPixels = Number(e.data.maxPixels) || 0, maxCoded = Number(e.data.maxCoded) || maxPixels;
    let decoder = null, images = [];
    const release = () => {
      for (const im of images) { try { im.free(); } catch (_) {} }
      try { if (decoder && decoder.decoder) { lib.heif_context_free(decoder.decoder); decoder.decoder = null; } } catch (_) {}
    };
    try {
      const bytes = new Uint8Array(buffer);
      decoder = new lib.HeifDecoder();
      images = decoder.decode(bytes);
      if (!images.length) throw Error('no image in file');
      // The size checked below is the one the file declares for the finished picture. The tiles it is put together from are a separate matter:
      // the library's own limit on any single coded picture is lowered from its default (about a gigapixel) to the largest photo the tool accepts.
      limitCodedPictures(decoder.decoder, maxCoded);
      const image = images.find(im => im.is_primary()) || images[0], width = image.get_width(), height = image.get_height();
      // Refuse before any pixel memory is allocated.
      if (!(width > 0 && height > 0)) throw Error('invalid size');
      if (width * height > maxPixels) throw Error('too large: ' + width + ' x ' + height);
      const out = new Uint8ClampedArray(width * height * 4);
      image.display({data: out, width, height}, shown => {
        try {
          if (!shown) throw Error('decoding failed');
          // libheif returns the numbers stored in the file. iPhone photos are Display P3: without this step every colour would be read as sRGB and come out duller.
          const colour = colourOf(bytes);
          if (colour === 'p3') p3ToSrgb(out);
          let opaque = true;
          for (let i = 3; i < out.length; i += 4) if (out[i] !== 255) { opaque = false; break; }
          postMessage({type: 'result', id, ok: true, width, height, opaque, colour, buffer: out.buffer}, [out.buffer]);
        } catch (err) { failed(id, err); }
        release();
      });
    } catch (err) { release(); failed(id, err); }
  };

  // libheif keeps its limits in a small structure per context: a version byte, then, as the first 64-bit field, the largest picture in pixels.
  // (The library's older call for this, heif_context_set_maximum_image_size_limit, has no effect in this build.)
  function limitCodedPictures(context, pixels) {
    try {
      const at = lib._heif_context_get_security_limits(context.$$.ptr), view = new DataView(lib.HEAPU8.buffer);
      if (at && view.getUint8(at) >= 1 && pixels >= 1) view.setBigUint64(at + 8, BigInt(Math.floor(pixels)), true);
    } catch (_) {}
  }

  // Which colour space the primary image declares: 'p3', 'srgb', 'other', or '' when nothing is declared (then sRGB is assumed).
  function colourOf(bytes) {
    try {
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      const tag = o => String.fromCharCode(bytes[o], bytes[o + 1], bytes[o + 2], bytes[o + 3]);
      const boxes = (start, end) => {
        const list = [];
        for (let o = start; o + 8 <= end;) {
          let size = dv.getUint32(o), head = 8;
          if (size === 1) { if (o + 16 > end) break; size = dv.getUint32(o + 8) * 4294967296 + dv.getUint32(o + 12); head = 16; } else if (size === 0) size = end - o;
          if (size < head || o + size > end) break;
          list.push({type: tag(o + 4), start: o + head, end: o + size});
          o += size;
        }
        return list;
      };
      const meta = boxes(0, bytes.length).find(b => b.type === 'meta');
      if (!meta) return '';
      const inMeta = boxes(meta.start + 4, meta.end), iprp = inMeta.find(b => b.type === 'iprp');
      if (!iprp) return '';
      const inIprp = boxes(iprp.start, iprp.end), ipco = inIprp.find(b => b.type === 'ipco');
      if (!ipco) return '';
      const props = boxes(ipco.start, ipco.end), pitm = inMeta.find(b => b.type === 'pitm');
      const primary = pitm ? (dv.getUint8(pitm.start) === 0 ? dv.getUint16(pitm.start + 4) : dv.getUint32(pitm.start + 4)) : -1;
      let own = [];
      for (const ipma of inIprp.filter(b => b.type === 'ipma')) {
        const version = dv.getUint8(ipma.start), wide = dv.getUint8(ipma.start + 3) & 1, count = dv.getUint32(ipma.start + 4);
        let o = ipma.start + 8;
        for (let n = 0; n < count && o < ipma.end; n++) {
          const item = version < 1 ? dv.getUint16(o) : dv.getUint32(o);
          o += version < 1 ? 2 : 4;
          const links = [], k = dv.getUint8(o++);
          for (let j = 0; j < k; j++) { links.push(wide ? dv.getUint16(o) & 0x7fff : dv.getUint8(o) & 0x7f); o += wide ? 2 : 1; }
          if (item === primary) own = links;
        }
      }
      const mine = own.map(i => props[i - 1]).filter(b => b && b.type === 'colr'), all = mine.length ? mine : props.filter(b => b.type === 'colr');
      // A file may carry both an ICC profile and an nclx description. The profile is the one that defines the colours.
      const icc = all.find(b => tag(b.start) === 'prof' || tag(b.start) === 'rICC'), nclx = all.find(b => tag(b.start) === 'nclx');
      if (!icc) {
        if (!nclx) return '';
        const primaries = dv.getUint16(nclx.start + 4), transfer = dv.getUint16(nclx.start + 6);
        if (transfer === 16 || transfer === 18) return 'other';   // PQ / HLG
        return primaries === 12 ? 'p3' : primaries === 1 ? 'srgb' : primaries === 2 ? '' : 'other';
      }
      // ICC profile: read the three colorant tags and compare them with the published Display P3 and sRGB values (D50).
      const base = icc.start + 4, count = Math.min(dv.getUint32(base + 128), 200), where = {};
      for (let i = 0; i < count; i++) {
        const entry = base + 132 + 12 * i;
        if (entry + 12 > icc.end) break;
        where[tag(entry)] = base + dv.getUint32(entry + 4);
      }
      const fixed = o => dv.getInt32(o) / 65536;
      const xyz = name => { const at = where[name]; return at && at + 20 <= icc.end && tag(at) === 'XYZ ' ? [fixed(at + 8), fixed(at + 12), fixed(at + 16)] : null; };
      const near = (a, b) => !!a && Math.abs(a[0] - b[0]) < .012 && Math.abs(a[1] - b[1]) < .012 && Math.abs(a[2] - b[2]) < .012;
      const red = xyz('rXYZ'), green = xyz('gXYZ'), blue = xyz('bXYZ');
      if (near(red, [.4361, .2225, .0139]) && near(green, [.3851, .7169, .0971]) && near(blue, [.1431, .0606, .7141])) return 'srgb';
      if (!(near(red, [.5151, .2412, -.0011]) && near(green, [.2920, .6922, .0419]) && near(blue, [.1571, .0666, .7841]))) return 'other';
      // What an ICC tone curve makes of the input 0.5, or null when the tag is absent or not understood.
      const toneAtHalf = (at, end) => {
        if (!at || at + 12 > end) return null;
        if (tag(at) === 'para') {
          const type = dv.getUint16(at + 8), params = [1, 3, 4, 5, 7][type];
          if (!params || at + 12 + 4 * params > end) return null;
          const p = n => fixed(at + 12 + 4 * n), a = type ? p(1) : 1, b = type ? p(2) : 0;
          if (type >= 3 && .5 < p(4)) return p(3) * .5 + (type === 4 ? p(6) : 0);
          return (a * .5 + b > 0 ? Math.pow(a * .5 + b, p(0)) : 0) + (type === 2 ? p(3) : type === 4 ? p(5) : 0);
        }
        if (tag(at) !== 'curv') return null;
        const n = dv.getUint32(at + 8);
        if (n === 0) return .5;
        if (n === 1) return at + 14 <= end ? Math.pow(.5, dv.getUint16(at + 12) / 256) : null;
        if (at + 12 + 2 * n > end) return null;
        const pos = .5 * (n - 1), lo = Math.floor(pos), hi = Math.min(n - 1, lo + 1), v = i => dv.getUint16(at + 12 + 2 * i) / 65535;
        return v(lo) + (v(hi) - v(lo)) * (pos - lo);
      };
      // Display P3 uses the sRGB tone curve, which maps one half to 0.214. Same primaries with a clearly different curve: leave the picture alone.
      const half = toneAtHalf(where.rTRC, icc.end);
      return half === null || (half > .19 && half < .24) ? 'p3' : 'other';
    } catch (_) { return ''; }
  }

  // Display P3 and sRGB share the transfer curve, so the conversion is: to linear light, one 3 x 3 matrix, back. Colours outside sRGB are clipped.
  function p3ToSrgb(px) {
    const lin = new Float32Array(256), enc = new Uint8Array(16385);
    for (let i = 0; i < 256; i++) { const c = i / 255; lin[i] = c <= .04045 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4); }
    for (let i = 0; i <= 16384; i++) { const c = i / 16384; enc[i] = Math.round(255 * (c <= .0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - .055)); }
    const code = v => enc[(v <= 0 ? 0 : v >= 1 ? 1 : v) * 16384 + .5 | 0];
    for (let i = 0; i < px.length; i += 4) {
      const r = lin[px[i]], g = lin[px[i + 1]], b = lin[px[i + 2]];
      px[i] = code(1.2249402 * r - .2249402 * g);
      px[i + 1] = code(-.0420570 * r + 1.0420570 * g);
      px[i + 2] = code(-.0196376 * r - .0786360 * g + 1.0982736 * b);
    }
  }
}
