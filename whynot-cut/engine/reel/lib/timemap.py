"""Source-time -> sequence-time mapping for pause removal (frame exact, no drift).

Edit decisions stay authored in SOURCE time (the transcript's clock). When pauses are removed, the
kept source ranges are laid back-to-back; each kept piece is quantised to whole sequence frames and
its source in-point is kept exact (Premiere ticks), so audio/video stay in sync inside every clip.
Jump cuts are masked by alternating a subtle scale on every other kept segment (camera decisions win).
"""
from __future__ import annotations

from .common import seq_fps


class TimeMap:
    def __init__(self, keep_ms: list, camera: list | None = None, mask_scales=(1.0, 1.06), max_scale: float = 1.2):
        """keep_ms: [(src_a, src_b)], camera: [{"at_ms","until_ms","scale_factor","type","decision_id",...}]"""
        self.frame_ms = 1000 / seq_fps()   # the client's sequence rate
        camera = sorted(camera or [], key=lambda c: c["at_ms"])
        self.pieces = []
        f, last_scale = 0, None
        lo, hi = mask_scales[0], mask_scales[-1]
        for k, (a, b) in enumerate(keep_ms):
            # alternate the zoom at every cut RELATIVE to what is on screen before it (visible change each cut)
            seg_scale = lo if (last_scale is None or last_scale != lo) else hi
            if k == 0:
                seg_scale = lo
            pts = sorted({a, b, *[c["at_ms"] for c in camera if a < c["at_ms"] < b],
                          *[c["until_ms"] for c in camera if a < c["until_ms"] < b]})
            for s, e in zip(pts, pts[1:]):
                n = round((e - s) / self.frame_ms)
                if n <= 0:
                    continue
                live = [c for c in camera if c["at_ms"] <= s < c["until_ms"]]
                cam = next((c for c in live if c.get("decision_id") == "AUTO_CUTAWAY"), live[-1] if live else None)
                scale = cam["scale_factor"] if cam else seg_scale
                at_cut = k > 0 and s == a          # first piece after a removed pause = a jump cut
                # no zoom flicker: a piece shorter than 8 frames keeps the previous zoom (never at a cut)
                if n < 8 and self.pieces and not cam and not at_cut:
                    scale = self.pieces[-1]["scale_factor"]
                # a jump cut must show a visible zoom change, also inside a punch-in that spans the cut:
                # step one mask increment further in (or out, if that would exceed max_scale)
                cutaway = bool(cam) and cam.get("decision_id") == "AUTO_CUTAWAY"   # a letterboxed card stays whole
                if at_cut and last_scale is not None and abs(scale - last_scale) < 1e-6 and not cutaway:
                    step = hi - lo
                    scale = round(scale + step, 4) if scale + step <= max_scale + 1e-9 else round(scale - step, 4)
                self.pieces.append({"src_in_ms": s, "src_out_ms": s + n * self.frame_ms, "start_frame": f,
                                    "end_frame": f + n, "keep_index": k, "scale_factor": scale,
                                    "camera": cam["type"] if cam else ("jumpcut_mask" if scale != 1.0 else "hold"),
                                    "decision_id": cam["decision_id"] if cam else None,
                                    "offset_x": cam.get("offset_x", 0.0) if cam else 0.0,
                                    "offset_y": cam.get("offset_y", 0.0) if cam else 0.0})
                f += n
                last_scale = scale
        self.total_frames = f

    def ms(self, t: float) -> float:
        """Source ms -> sequence ms. Times inside a removed pause snap to the next kept piece."""
        for p in self.pieces:
            if t < p["src_in_ms"]:
                return p["start_frame"] * self.frame_ms
            if t < p["src_out_ms"]:
                return p["start_frame"] * self.frame_ms + (t - p["src_in_ms"])
        return self.total_frames * self.frame_ms

    def frame(self, t: float) -> int:
        return int(self.ms(t) / self.frame_ms + 0.5)

    def removed(self, a: float, b: float) -> bool:
        """True if the whole source range [a,b) falls inside removed pauses."""
        return self.frame(a) >= self.frame(b)
