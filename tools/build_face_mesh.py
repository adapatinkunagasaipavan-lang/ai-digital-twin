"""Build assets/face_mesh.json from assets/photo.jpg  (run once per photo).

Needs a one-off environment (the newer mediapipe wheels no longer bundle the
face model, the 0.10.14 wheel does):

    python3.11 -m venv .mpvenv && source .mpvenv/bin/activate
    pip install mediapipe==0.10.14 opencv-python-headless scipy numpy shapely
    python tools/build_face_mesh.py            # writes assets/face_mesh.json
    python tools/build_face_mesh.py --debug    # also writes assets/face_mesh_debug.png

The browser avatar uses this file to turn the photo into a 3D mesh that can
turn its head, open its jaw and blink. No ML runs in the browser.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]

# MediaPipe FaceMesh landmark groups
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
        152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
INNER_UP = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]
INNER_LO = [324, 318, 402, 317, 14, 87, 178, 88, 95]        # right -> left (closes the loop)
OUTER_LO = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]
CORNERS = [78, 308, 61, 291]
EYE_A = {"up": [246, 161, 160, 159, 158, 157, 173], "lo": [33, 7, 163, 144, 145, 153, 154, 155, 133]}
EYE_B = {"up": [466, 388, 387, 386, 385, 384, 398], "lo": [263, 249, 390, 373, 374, 380, 381, 382, 362]}


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", default=str(ROOT / "assets" / "photo.jpg"))
    ap.add_argument("--out", default=str(ROOT / "assets" / "face_mesh.json"))
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    img = cv2.imread(a.photo)
    H, W = img.shape[:2]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1,
                                         refine_landmarks=True) as fm:
        res = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        raise SystemExit("No face found. Use a clear, front-facing photo.")
    lm = res.multi_face_landmarks[0].landmark[:468]
    P = np.array([[l.x * W, l.y * H, -l.z * W] for l in lm], dtype=np.float64)  # z>0 = towards viewer
    P[:, 2] -= P[OVAL, 2].mean() - 0  # centre depth around the face outline

    oval = P[OVAL, :2].astype(np.float32).reshape(-1, 1, 2)

    def sdist(pt):  # >0 inside the face oval
        return cv2.pointPolygonTest(oval, (float(pt[0]), float(pt[1])), True)

    # ---- extra points: a grid over the whole image so the mesh covers hair, neck, shoulders
    pts, zs = [p for p in P[:, :2]], list(P[:, 2])
    step = 36
    for gy in np.arange(0, H + 1, step):
        for gx in np.arange(0, W + 1, step):
            g = np.array([min(gx, W), min(gy, H)], dtype=float)
            d_in = sdist(g)
            if d_in > -10:                                  # inside / right at the face outline
                continue
            if np.min(np.linalg.norm(P[:, :2] - g, axis=1)) < 24:
                continue
            k = int(np.argmin(np.linalg.norm(P[OVAL, :2] - g, axis=1)))
            fall = 1 - smoothstep(0, 140, -d_in)
            pts.append(g)
            zs.append(P[OVAL[k], 2] * fall)
    pts = np.array(pts)
    Z = np.array(zs)
    n = len(pts)

    # ---- triangulate using a *virtually opened* mouth so the cavity becomes a real hole
    virt = pts.copy()
    lower_inner = [i for i in INNER_LO if i not in CORNERS]
    mhalf = (P[308, 0] - P[78, 0]) / 2
    lip_body = [i for i in range(468)
                if P[13, 1] + 3 < P[i, 1] < P[17, 1] + 4 and abs(P[i, 0] - (P[13, 0] + P[14, 0]) / 2) <= 1.05 * mhalf
                and i not in INNER_LO]
    virt[lower_inner + lip_body, 1] += 16                  # lower lip moves down together in the virtual layout
    tri = Delaunay(virt).simplices
    hole = Polygon(virt[INNER_UP + INNER_LO]).buffer(0)

    up_set = {i for i in INNER_UP if i not in CORNERS}
    lo_set = set(lower_inner)

    def in_hole(t):                                       # triangle overlapping the opened mouth
        vs = {int(v) for v in t}
        if vs & up_set and vs & lo_set:                   # bridges upper and lower inner lip
            return True
        a = Polygon(virt[[int(v) for v in t]])
        return a.area > 0 and hole.intersection(a).area > 0.25 * a.area

    tri = np.array([t for t in tri if not in_hole(t)], dtype=np.int32)

    # ---- per-vertex region weights
    mx = float((P[13, 0] + P[14, 0]) / 2)
    my = float((P[13, 1] + P[14, 1]) / 2)
    mouth_half = float((P[308, 0] - P[78, 0]) / 2)
    lip_bottom = float(P[17, 1])
    chin = float(P[152, 1])
    half_jaw = float((P[397, 0] - P[172, 0]) / 2)

    w_head = np.zeros(n)
    w_jaw = np.zeros(n)
    w_mouth = np.zeros(n)
    w_blink = {"a": np.zeros(n), "b": np.zeros(n)}
    for i, p in enumerate(pts):
        d = sdist(p)
        w_head[i] = 1.0 if d >= 0 else 1 - smoothstep(0, 120, -d)
        if p[1] > my:
            ramp = np.clip((p[1] - my) / max(0.35 * (lip_bottom - my), 1), 0, 1)
            below = 1 - smoothstep(chin, chin + 0.7 * (chin - my), p[1])
            side = 1 - smoothstep(0.55, 1.05, abs(p[0] - mx) / half_jaw)
            w_jaw[i] = ramp * below * side
        rx, ry = 1.7 * mouth_half, 1.3 * mouth_half
        w_mouth[i] = np.exp(-(((p[0] - mx) / rx) ** 2 + ((p[1] - my) / ry) ** 2))
    for i in INNER_LO + OUTER_LO + lip_body:
        w_jaw[i] = 1.0
    for i in INNER_UP:
        w_jaw[i] = 0.0
    for i in [0, 37, 39, 40, 185, 267, 269, 270, 409]:
        w_jaw[i] = 0.0
    for i in CORNERS:
        w_jaw[i] = 0.6
    for i in (95, 324, 146, 375):
        w_jaw[i] = 0.85

    eye_h = {}
    for key, e in (("a", EYE_A), ("b", EYE_B)):
        up, lo = P[e["up"]], P[e["lo"]]
        cx, cy = up[:, 0].mean(), up[:, 1].mean()
        h = max(float(lo[:, 1].mean() - up[:, 1].mean()), 4.0)
        wd = float(lo[:, 0].max() - lo[:, 0].min())
        eye_h[key] = h
        for i, p in enumerate(pts):
            g = np.exp(-(((p[0] - cx) / (0.62 * wd)) ** 2 + ((p[1] - (cy - 0.4 * h)) / (1.5 * h)) ** 2))
            w_blink[key][i] = g
        for i in e["lo"]:
            w_blink[key][i] = 0.0
        for i in e["up"]:
            w_blink[key][i] = 1.0

    # ---- rest-pose normals (for subtle shading that follows head turns)
    nrm = np.zeros((n, 3))
    V = np.column_stack([pts, Z])
    for t in tri:
        c = np.cross(V[t[1]] - V[t[0]], V[t[2]] - V[t[0]])
        if c[2] < 0:
            c = -c
        for v in t:
            nrm[v] += c
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)

    r3 = lambda a: [round(float(x), 3) for x in np.ravel(a)]
    out = {
        "W": W, "H": H, "n": n,
        "pos": r3(V), "nrm": r3(nrm),
        "idx": [int(i) for i in tri.ravel()],
        "wHead": r3(w_head), "wJaw": r3(w_jaw), "wMouth": r3(w_mouth),
        "wBlinkA": r3(w_blink["a"]), "wBlinkB": r3(w_blink["b"]),
        "eyeHA": eye_h["a"], "eyeHB": eye_h["b"],
        "mouth": [mx, my], "mouthHalf": mouth_half, "lipBottom": lip_bottom, "chin": chin,
        "pivot": [float(P[1, 0]), float(P[152, 1] + 0.35 * (chin - my)), 0.0],
        "innerUp": INNER_UP, "innerLo": INNER_LO,
    }
    Path(a.out).write_text(json.dumps(out, separators=(",", ":")))
    print(f"vertices={n} triangles={len(tri)} -> {a.out} ({Path(a.out).stat().st_size/1024:.0f} KB)")

    if a.debug:
        dbg = img.copy()
        for t in tri:
            cv2.polylines(dbg, [pts[t].astype(np.int32)], True, (0, 255, 255), 1)
        for i in INNER_UP + INNER_LO:
            cv2.circle(dbg, tuple(int(v) for v in pts[i]), 2, (0, 0, 255), -1)
        cv2.imwrite(str(Path(a.out).with_name("face_mesh_debug.png")), dbg)


if __name__ == "__main__":
    main()
