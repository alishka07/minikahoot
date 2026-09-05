// Offline QR generator — byte mode, version 4, EC level M (up to 62 bytes). No deps.
(function () {
  var SIZE = 33, EXP = new Array(256), LOG = new Array(256);
  (function () { var x = 1; for (var i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11d; } })();
  function mul(a, b) { return (a === 0 || b === 0) ? 0 : EXP[(LOG[a] + LOG[b]) % 255]; }
  function genPoly(n) {
    var g = [1];
    for (var i = 0; i < n; i++) {
      var next = new Array(g.length + 1).fill(0);
      for (var j = 0; j < g.length; j++) { next[j] ^= g[j]; next[j + 1] ^= mul(g[j], EXP[i]); }
      g = next;
    }
    return g;
  }
  function ecc(data, n) {
    var g = genPoly(n), res = data.concat(new Array(n).fill(0));
    for (var i = 0; i < data.length; i++) {
      var c = res[i]; if (!c) continue;
      for (var j = 0; j < g.length; j++) res[i + j] ^= mul(g[j], c);
    }
    return res.slice(data.length);
  }
  function bitLen(v) { var n = 0; while (v) { n++; v >>>= 1; } return n; }
  function fmtBits(ecl, mask) {
    var data = (ecl << 3) | mask, d = data << 10;
    while (bitLen(d) - 11 >= 0) d ^= 0x537 << (bitLen(d) - 11);
    return ((data << 10) | d) ^ 0x5412;
  }
  function maskAt(k, i, j) {
    switch (k) {
      case 0: return (i + j) % 2 === 0;
      case 1: return i % 2 === 0;
      case 2: return j % 3 === 0;
      case 3: return (i + j) % 3 === 0;
      case 4: return (Math.floor(i / 2) + Math.floor(j / 3)) % 2 === 0;
      case 5: return ((i * j) % 2) + ((i * j) % 3) === 0;
      case 6: return (((i * j) % 2) + ((i * j) % 3)) % 2 === 0;
      default: return (((i + j) % 2) + ((i * j) % 3)) % 2 === 0;
    }
  }
  function bitsFor(text) {
    var bytes = [], enc = new TextEncoder().encode(text);
    for (var i = 0; i < enc.length; i++) bytes.push(enc[i]);
    if (bytes.length > 62) bytes = bytes.slice(0, 62);
    var bits = [];
    function put(v, n) { for (var b = n - 1; b >= 0; b--) bits.push((v >> b) & 1); }
    put(4, 4); put(bytes.length, 8);
    bytes.forEach(function (b) { put(b, 8); });
    var cap = 64 * 8;
    put(0, Math.min(4, cap - bits.length));
    while (bits.length % 8) bits.push(0);
    var pads = [0xEC, 0x11], p = 0;
    while (bits.length < cap) { put(pads[p++ % 2], 8); }
    var cw = [];
    for (var k = 0; k < bits.length; k += 8) {
      var v = 0; for (var q = 0; q < 8; q++) v = (v << 1) | bits[k + q];
      cw.push(v);
    }
    var b0 = cw.slice(0, 32), b1 = cw.slice(32, 64);
    var e0 = ecc(b0, 18), e1 = ecc(b1, 18), out = [];
    for (var d = 0; d < 32; d++) { out.push(b0[d]); out.push(b1[d]); }
    for (var e = 0; e < 18; e++) { out.push(e0[e]); out.push(e1[e]); }
    var stream = [];
    out.forEach(function (byte) { for (var b = 7; b >= 0; b--) stream.push((byte >> b) & 1); });
    return stream;
  }
  function skeleton() {
    var m = [], fn = [], r, c;
    for (r = 0; r < SIZE; r++) { m.push(new Array(SIZE).fill(0)); fn.push(new Array(SIZE).fill(false)); }
    function set(rr, cc, v) { if (rr < 0 || cc < 0 || rr >= SIZE || cc >= SIZE) return; m[rr][cc] = v ? 1 : 0; fn[rr][cc] = true; }
    [[0, 0], [0, SIZE - 7], [SIZE - 7, 0]].forEach(function (p) {
      for (var i = -1; i <= 7; i++) for (var j = -1; j <= 7; j++) {
        var on = (i >= 0 && i <= 6 && (j === 0 || j === 6)) || (j >= 0 && j <= 6 && (i === 0 || i === 6)) || (i >= 2 && i <= 4 && j >= 2 && j <= 4);
        set(p[0] + i, p[1] + j, on);
      }
    });
    for (var i2 = -2; i2 <= 2; i2++) for (var j2 = -2; j2 <= 2; j2++)
      set(26 + i2, 26 + j2, Math.max(Math.abs(i2), Math.abs(j2)) !== 1);
    for (var k = 8; k < SIZE - 8; k++) { set(6, k, k % 2 === 0); set(k, 6, k % 2 === 0); }
    set(SIZE - 8, 8, true);
    for (var f = 0; f <= 8; f++) { if (!fn[8][f]) set(8, f, false); if (!fn[f][8]) set(f, 8, false); }
    for (var g = SIZE - 8; g < SIZE; g++) if (!fn[8][g]) set(8, g, false);
    for (var h = SIZE - 7; h < SIZE; h++) if (!fn[h][8]) set(h, 8, false);
    return { m: m, fn: fn };
  }
  function place(stream, mask) {
    var s = skeleton(), m = s.m, fn = s.fn, dir = -1, row = SIZE - 1, col = SIZE - 1, idx = 0;
    while (col > 0) {
      if (col === 6) col--;
      while (true) {
        for (var t = 0; t < 2; t++) {
          var cc = col - t;
          if (!fn[row][cc]) {
            var dark = idx < stream.length ? stream[idx++] === 1 : false;
            if (maskAt(mask, row, cc)) dark = !dark;
            m[row][cc] = dark ? 1 : 0;
          }
        }
        row += dir;
        if (row < 0 || row >= SIZE) { row -= dir; dir = -dir; break; }
      }
      col -= 2;
    }
    var bits = fmtBits(0, mask);
    for (var i = 0; i < 15; i++) {
      var v = ((bits >> i) & 1) ? 1 : 0;
      if (i < 6) m[i][8] = v; else if (i < 8) m[i + 1][8] = v; else m[SIZE - 15 + i][8] = v;
      if (i < 8) m[8][SIZE - i - 1] = v; else if (i === 8) m[8][7] = v; else m[8][15 - i - 1] = v;
    }
    m[SIZE - 8][8] = 1;
    return m;
  }
  function penalty(m) {
    var p = 0, i, j, dark = 0;
    function run(get) {
      var total = 0;
      for (i = 0; i < SIZE; i++) {
        var len = 1;
        for (j = 1; j < SIZE; j++) {
          if (get(i, j) === get(i, j - 1)) len++;
          else { if (len >= 5) total += 3 + (len - 5); len = 1; }
        }
        if (len >= 5) total += 3 + (len - 5);
      }
      return total;
    }
    p += run(function (a, b) { return m[a][b]; });
    p += run(function (a, b) { return m[b][a]; });
    for (i = 0; i < SIZE - 1; i++) for (j = 0; j < SIZE - 1; j++) {
      var v = m[i][j];
      if (v === m[i][j + 1] && v === m[i + 1][j] && v === m[i + 1][j + 1]) p += 3;
    }
    for (i = 0; i < SIZE; i++) for (j = 0; j < SIZE; j++) dark += m[i][j];
    p += Math.floor(Math.abs((dark * 100) / (SIZE * SIZE) - 50) / 5) * 10;
    return p;
  }
  function matrix(text) {
    var best = null, bestP = Infinity, stream = bitsFor(text);
    for (var k = 0; k < 8; k++) {
      var m = place(stream, k), p = penalty(m);
      if (p < bestP) { bestP = p; best = m; }
    }
    return best;
  }
  function render(canvas, text, opts) {
    if (!canvas) return;
    opts = opts || {};
    var quiet = opts.quiet == null ? 2 : opts.quiet;
    var dark = opts.dark || '#07050d', light = opts.light || '#ffffff';
    var m = matrix(text), total = SIZE + quiet * 2;
    var px = Math.max(1, Math.floor((opts.size || canvas.width || 188) / total));
    var dim = px * total;
    canvas.width = dim; canvas.height = dim;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = light; ctx.fillRect(0, 0, dim, dim);
    ctx.fillStyle = dark;
    for (var r = 0; r < SIZE; r++) for (var c = 0; c < SIZE; c++)
      if (m[r][c]) ctx.fillRect((c + quiet) * px, (r + quiet) * px, px, px);
  }
  window.NQ_QR = { render: render, matrix: matrix };
})();
