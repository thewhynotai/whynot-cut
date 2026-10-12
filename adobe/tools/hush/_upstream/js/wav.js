/* Hush - WAV reader (pure). Uint8Array of a .wav file -> {sampleRate, samples: Float32Array (mono mix)} */
(function (root) {
    'use strict';
    var W = {};

    W.header = function (bytes, dv) {
        function tag(o) { return String.fromCharCode(bytes[o], bytes[o + 1], bytes[o + 2], bytes[o + 3]); }
        if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE') { throw new Error('Not a WAV file'); }
        var off = 12, fmt = null, dataOff = -1, dataLen = 0;
        while (off + 8 <= bytes.length) {
            var id = tag(off), len = dv.getUint32(off + 4, true);
            if (id === 'fmt ') {
                fmt = { format: dv.getUint16(off + 8, true), channels: dv.getUint16(off + 10, true),
                        rate: dv.getUint32(off + 12, true), bits: dv.getUint16(off + 22, true) };
                if (fmt.format === 0xFFFE && len >= 26) { fmt.format = dv.getUint16(off + 32, true); }
            } else if (id === 'data') {
                dataOff = off + 8;
                dataLen = Math.min(len, bytes.length - dataOff); // len can be 0/garbage on streamed files
                if (len === 0 || len === 0xFFFFFFFF) { dataLen = bytes.length - dataOff; }
                break;
            }
            off += 8 + len + (len & 1);
        }
        if (!fmt || dataOff < 0) { throw new Error('WAV has no fmt/data chunk'); }
        return { format: fmt.format, channels: fmt.channels, rate: fmt.rate, bits: fmt.bits, dataOff: dataOff, dataLen: dataLen };
    };

    W.sample = function (bytes, dv, p, format, bps) {
        if (format === 3) { return bps === 8 ? dv.getFloat64(p, true) : dv.getFloat32(p, true); }
        if (bps === 2) { return dv.getInt16(p, true) / 32768; }
        if (bps === 3) { return ((bytes[p] | (bytes[p + 1] << 8) | (bytes[p + 2] << 16)) << 8 >> 8) / 8388608; }
        if (bps === 4) { return dv.getInt32(p, true) / 2147483648; }
        return (bytes[p] - 128) / 128;
    };

    W.decode = function (bytes) {
        var dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        var h = W.header(bytes, dv), fmt = { format: h.format, channels: h.channels, rate: h.rate, bits: h.bits };
        var dataOff = h.dataOff, dataLen = h.dataLen;
        var bps = fmt.bits / 8, ch = fmt.channels, frames = Math.floor(dataLen / (bps * ch));
        var out = new Float32Array(frames), i, c, sum, p;
        for (i = 0; i < frames; i++) {
            sum = 0;
            for (c = 0; c < ch; c++) {
                p = dataOff + (i * ch + c) * bps;
                sum += W.sample(bytes, dv, p, fmt.format, bps);
            }
            out[i] = sum / ch;
        }
        return { sampleRate: fmt.rate, samples: out, channels: ch };
    };

    /* level envelope straight from the file bytes (no full float copy; long podcasts stay small in memory) */
    W.envelope = function (bytes, hop) {
        var dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        var h = W.header(bytes, dv), bps = h.bits / 8, ch = h.channels;
        var frames = Math.floor(h.dataLen / (bps * ch)), n = Math.max(1, Math.round(h.rate * hop));
        var count = Math.ceil(frames / n), env = new Float32Array(count), i, f, c, p, v, sum, end;
        for (i = 0; i < count; i++) {
            sum = 0; end = Math.min(frames, (i + 1) * n);
            for (f = i * n; f < end; f++) {
                v = 0;
                for (c = 0; c < ch; c++) { p = h.dataOff + (f * ch + c) * bps; v += W.sample(bytes, dv, p, h.format, bps); }
                v /= ch; sum += v * v;
            }
            v = Math.sqrt(sum / Math.max(1, end - i * n));
            env[i] = v > 1e-5 ? 20 * Math.log10(v) : -100;
        }
        return { env: env, duration: frames / h.rate, sampleRate: h.rate };
    };

    root.HushWav = W;
})(typeof window !== 'undefined' ? window : this);
