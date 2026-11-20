#!/usr/bin/env python3
"""Generates the animated SVGs in ../assets for the GitHub profile README.

Styled after the CV: grey paper, charcoal name band, CMU Serif for math,
Roboto Condensed for headings, IBM Plex Mono for the terminal bits.
Fonts are subset and embedded so every visitor sees the same thing, and all
animation is SMIL/CSS (GitHub's image proxy strips JS but keeps these).

    python3 tools/build.py          # needs fontTools; font paths below
"""
import base64
import io
import math
import random
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

TEX = "/usr/local/texlive/2023/texmf-dist/fonts/opentype"
FLUTTER = "/usr/local/share/flutter/bin/cache/artifacts/material_fonts"
FONTS = {
    "cmu-it": f"{TEX}/public/cm-unicode/cmunti.otf",   # CMU Serif Italic
    "cmu-rm": f"{TEX}/public/cm-unicode/cmunrm.otf",     # CMU Serif Roman
    "rc": f"{FLUTTER}/RobotoCondensed-Regular.ttf",
    "rc-bold": f"{FLUTTER}/RobotoCondensed-Bold.ttf",
    "plex": f"{TEX}/ibm/plex/IBMPlexMono-Regular.otf",
}
FALLBACK = {
    "cmu-it": "Georgia,serif", "cmu-rm": "Georgia,serif",
    "rc": "'Arial Narrow',sans-serif", "rc-bold": "'Arial Narrow',sans-serif",
    "plex": "Menlo,Consolas,monospace",
}

# CV palette
PAPER, BAND, INK, MUTED, RULE = "#e3e3e3", "#474747", "#2e2e2e", "#7c7c7c", "#bcbcbc"
ON_BAND, ON_BAND_MUTED = "#f4f4f4", "#a9a9a9"
CYAN, PINK, ORANGE, LIME, PURPLE = "#4cc9e6", "#e8246f", "#f29620", "#8fcf2c", "#8a5cf5"

_tt = {k: TTFont(v) for k, v in FONTS.items()}


def width(text, font, size):
    tt = _tt[font]
    cmap, hmtx, upm = tt.getBestCmap(), tt["hmtx"], tt["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(ch), cmap[ord("?")])][0] for ch in text) * size / upm


def f(x):
    return f"{x:.2f}".rstrip("0").rstrip(".")


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Doc:
    """Collects SVG body + which glyphs of which font were used, then embeds subsets."""

    def __init__(self, w, h):
        self.w, self.h, self.parts, self.used, self.css = w, h, [], {}, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, font="rc", size=14, fill=INK, anchor="start", extra=""):
        self.used.setdefault(font, set()).update(s)
        return (f'<text x="{f(x)}" y="{f(y)}" font-family="\'{font}\',{FALLBACK[font]}" '
                f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')

    def tspan(self, s, font, fill=None):
        self.used.setdefault(font, set()).update(s)
        c = f' fill="{fill}"' if fill else ""
        return f'<tspan font-family="\'{font}\',{FALLBACK[font]}"{c}>{esc(s)}</tspan>'

    def math(self, x, y, items, size, color=INK, anchor="middle", stroke=None):
        """Lay out a run of math. items: (text, font[, color]) or '<' / '>' for angle brackets
        (CMU has no ⟨⟩ glyphs, so they're drawn as hairline paths)."""
        bw = size * 0.24
        sw = stroke or size * 0.042
        total = sum(bw if isinstance(it, str) else width(it[0], it[1], size) for it in items)
        cx = x - total / 2 if anchor == "middle" else x
        out = []
        for it in items:
            if isinstance(it, str):
                top, bot, mid = y - size * 0.74, y + size * 0.24, y - size * 0.25
                a, b_ = (cx + bw * 0.82, cx + bw * 0.18) if it == "<" else (cx + bw * 0.18, cx + bw * 0.82)
                out.append(f'<path d="M{f(a)} {f(top)} L{f(b_)} {f(mid)} L{f(a)} {f(bot)}" fill="none" '
                           f'stroke="{color}" stroke-width="{f(sw)}" stroke-linejoin="miter"/>')
                cx += bw
            else:
                s, font = it[0], it[1]
                col = it[2] if len(it) > 2 else color
                out.append(self.text(cx, y, s, font, size, col))
                cx += width(s, font, size)
        return "".join(out), total

    def render(self):
        faces = []
        for font, chars in self.used.items():
            opts = subset.Options()
            opts.flavor = "woff"
            opts.layout_features = ["kern"]
            opts.name_IDs = []
            opts.notdef_outline = True
            sub = subset.Subsetter(opts)
            tt = TTFont(FONTS[font])
            sub.populate(text="".join(sorted(chars)) + " ")
            sub.subset(tt)
            buf = io.BytesIO()
            tt.flavor = "woff"
            tt.save(buf)
            b64 = base64.b64encode(buf.getvalue()).decode()
            faces.append(f"@font-face{{font-family:'{font}';src:url(data:font/woff;base64,{b64}) format('woff')}}")
        style = "".join(faces + self.css)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img">\n<style>{style}</style>\n'
                + "\n".join(self.parts) + "\n</svg>\n")


def paper(d, rx=6):
    d.add(f'<rect width="{d.w}" height="{d.h}" rx="{rx}" fill="{PAPER}"/>')


def typed(d, key, x, y, segments, size, t_on, t_off, T, cps=28, font="plex"):
    """Mono text revealed one character at a time from t_on, hidden at t_off (seconds in a T loop).
    Returns the list of (time, cursor_x) events."""
    cw = width("M", font, size)
    n = sum(len(s) for s, _ in segments)
    ev = [(0.0, 0)]
    for k in range(n + 1):
        ev.append((t_on + k / cps, k * cw))
    if t_off < T:
        ev.append((t_off, 0))
    ev = sorted(set(ev))
    kt = ";".join(f(t / T) for t, _ in ev)
    vals = ";".join(f(w) for _, w in ev)
    end = "" if ev[-1][0] >= T else f";1"
    endv = "" if ev[-1][0] >= T else f";{f(ev[-1][1])}"
    d.add(f'<clipPath id="{key}"><rect x="{f(x)}" y="{f(y-size)}" height="{f(size*1.5)}" width="0">'
          f'<animate attributeName="width" dur="{T}s" repeatCount="indefinite" calcMode="discrete" '
          f'keyTimes="{kt}{end}" values="{vals}{endv}"/></rect></clipPath>')
    spans = "".join(d.tspan(s, font, c) for s, c in segments)
    d.add(f'<text clip-path="url(#{key})" x="{f(x)}" y="{f(y)}" font-size="{size}" xml:space="preserve">{spans}</text>')
    return [(t, x + w) for t, w in ev if t > 0]


# --------------------------------------------------------------------------- header
def header():
    d = Doc(1000, 236)
    W, BH = d.w, 142
    d.add(f'<clipPath id="card"><rect width="{W}" height="{d.h}" rx="6"/></clipPath>')
    d.add(f'<g clip-path="url(#card)"><rect width="{W}" height="{d.h}" fill="{PAPER}"/>'
          f'<rect width="{W}" height="{BH}" fill="{BAND}"/></g>')

    m, _ = d.math(W / 2, 100, ["<", ("Roy", "cmu-it"), ("|", "cmu-rm"), ("Medina", "cmu-it"), ">"],
                  82, color=ON_BAND, stroke=2.4)
    d.add(m)

    # terminal
    size, y = 19, 188
    prompt = "roy@observer:~$ "
    px = 64
    d.add(d.text(px, y, prompt, "plex", size, MUTED, extra='xml:space="preserve"'))
    x0 = px + width(prompt, "plex", size)
    lines = ["echo \"Physicist by day,\"",
             "echo \"programmer by night,\"",
             "echo \"mathematician when the stakes are high.\""]
    slot, T = 4.0, 12.0
    cursor = []
    for i, line in enumerate(lines):
        cmd, arg = line.split(" ", 1)
        cursor += typed(d, f"t{i}", x0, y, [(cmd + " ", MUTED), (arg, INK)], size,
                        i * slot + 0.2, (i + 1) * slot - 0.25, T, cps=24)
    cursor.sort()
    kt = "0;" + ";".join(f(t / T) for t, _ in cursor)
    vals = f"{f(x0)};" + ";".join(f(x) for _, x in cursor)
    d.add(f'<rect class="blink" x="{f(x0)}" y="{y-size+3}" width="{f(width("M","plex",size))}" '
          f'height="{size+3}" fill="{INK}"><animate attributeName="x" dur="{T}s" repeatCount="indefinite" '
          f'calcMode="discrete" keyTimes="{kt}" values="{vals}"/></rect>')
    d.add(d.text(px, y + 30, "# 1.8k+ stars, 3k+ users from 140+ countries",
                 "plex", 12.5, MUTED, extra='xml:space="preserve"'))
    d.css.append(".blink{animation:b 1.1s steps(1) infinite}@keyframes b{50%{opacity:0}}")
    return d.render()


# --------------------------------------------------------------------------- bloch sphere
def bloch():
    d = Doc(380, 380)
    paper(d)
    cx, cy, R = 190, 192, 128
    se = 0.30
    ce = math.sqrt(1 - se * se)

    def proj(th, ph):
        x, y, z = math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)
        return cx + R * x, cy - R * (z * ce - y * se)

    T, dt, TH = 18.0, 0.05, 1.0

    def ease(u):
        u = max(0.0, min(1.0, u))
        return u * u * (3 - 2 * u)

    def theta(t):
        for a, b_, th0, th1 in [(5, 6, TH, 0), (7.5, 8.5, 0, TH), (13, 14, TH, math.pi), (15.5, 16.5, math.pi, TH)]:
            if a <= t < b_:
                return th0 + (th1 - th0) * ease(t - a)
        if 6 <= t < 7.5: return 0.0
        if 14 <= t < 15.5: return math.pi
        return TH

    xs, ys, kt = [], [], []
    for k in range(int(T / dt) + 1):
        t = k * dt
        sx, sy = proj(theta(t), math.pi * t)  # 9 turns per loop → seamless
        xs.append(f(sx)); ys.append(f(sy)); kt.append(f(t / T))
    KT = ";".join(kt)

    def anim(attr, vals):
        return (f'<animate attributeName="{attr}" dur="{T}s" repeatCount="indefinite" '
                f'keyTimes="{KT}" values="{";".join(vals)}"/>')

    dash = f'fill="none" stroke="{MUTED}" stroke-width="0.9" stroke-dasharray="4 4"'
    d.add(f'<circle cx="{cx}" cy="{cy}" r="{R}" {dash}/>')
    d.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{R}" ry="{f(R*se)}" {dash}/>')
    d.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{R}" ry="{f(R*ce)}" {dash} opacity="0.7">'
          f'<animate attributeName="rx" values="{R};{f(R*0.08)};{R}" dur="8s" repeatCount="indefinite"/></ellipse>')
    ny, sy_ = cy - R * ce, cy + R * ce
    d.add(f'<line x1="{cx}" y1="{f(ny)}" x2="{cx}" y2="{f(sy_)}" stroke="{MUTED}" stroke-width="1"/>')

    m, _ = d.math(cx, ny - 22, [("|", "cmu-rm"), ("Quantum", "cmu-it"), ">"], 17)
    d.add(m)
    m, _ = d.math(cx, sy_ + 38, [("|", "cmu-rm"), ("Computing", "cmu-it"), ">"], 17)
    d.add(m)

    for py, t0, color in [(ny, 6.0, CYAN), (sy_, 14.0, LIME)]:
        k = f"0;{f(t0/T)};{f((t0+1.4)/T)};1"
        d.add(f'<circle cx="{cx}" cy="{f(py)}" r="0" fill="none" stroke="{color}" stroke-width="1.2">'
              f'<animate attributeName="r" dur="{T}s" repeatCount="indefinite" keyTimes="{k}" values="0;0;30;30"/>'
              f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" keyTimes="{k}" values="0;1;0;0"/>'
              f'</circle>')

    # terminal readout

    d.add(f'<defs><marker id="ah" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" '
          f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{INK}"/></marker></defs>')
    d.add(f'<line x1="{cx}" y1="{cy}" x2="{xs[0]}" y2="{ys[0]}" stroke="{INK}" stroke-width="1.4" '
          f'marker-end="url(#ah)">{anim("x2", xs)}{anim("y2", ys)}</line>')
    d.add(f'<circle cx="{cx}" cy="{cy}" r="2.2" fill="{INK}"/>')
    lbl, _ = d.math(0, 0, [("|", "cmu-rm"), ("Roy", "cmu-it"), ">"], 16, anchor="start")
    fade = f"0;{f(5.5/T)};{f(5.8/T)};{f(8.0/T)};{f(8.3/T)};{f(13.5/T)};{f(13.8/T)};{f(16.0/T)};{f(16.3/T)};1"
    d.add(f'<g transform="translate({xs[0]} {ys[0]})"><g transform="translate(10 -8)">{lbl}'
          f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" keyTimes="{fade}" '
          f'values="1;1;0;0;1;1;0;0;1;1"/></g>'
          f'<animateTransform attributeName="transform" type="translate" dur="{T}s" repeatCount="indefinite" '
          f'keyTimes="{KT}" values="{";".join(f"{x} {y}" for x, y in zip(xs, ys))}"/></g>')
    return d.render()


# --------------------------------------------------------------------------- observer
def observer():
    d = Doc(1000, 266)
    paper(d)
    d.add(d.text(36, 66, "Observer AI", "rc-bold", 30, INK))
    stats = [("1.8k", "GitHub stars"), ("3k", "signed-in users"), ("140+", "countries"), ("150+", "forks")]
    for i, (big, small) in enumerate(stats):
        x, y = 36 + (i % 2) * 140, 136 + (i // 2) * 62
        d.add(d.text(x, y, big, "rc-bold", 30, INK))
        d.add(d.text(x, y + 20, small, "rc", 13, MUTED))
    d.add(f'<line x1="350" y1="36" x2="350" y2="{d.h-36}" stroke="{RULE}"/>')

    X0, SW, P, T = 384, 584, 584, 9.0
    base, thresh = 138, 82
    rnd = random.Random(7)
    noise = [rnd.uniform(-3.5, 3.5) for _ in range(P // 4 + 1)]
    noise[-1] = noise[0]
    spikes, bumps = [(150, 76), (350, 82), (520, 72)], [(70, 26), (255, 32), (440, 22)]

    def sig(s):
        s %= P
        i = int(s // 4)
        fr = (s - i * 4) / 4
        y = base + noise[i] * (1 - fr) + noise[min(i + 1, len(noise) - 1)] * fr
        for c, a in spikes:
            y -= a * math.exp(-((s - c) / 8) ** 2)
        for c, a in bumps:
            y -= a * math.exp(-((s - c) / 15) ** 2)
        return y

    d.add(f'<clipPath id="sc"><rect x="{X0}" y="20" width="{SW}" height="140"/></clipPath>')
    d.add(f'<line x1="{X0}" y1="{base+14}" x2="{X0+SW}" y2="{base+14}" stroke="{RULE}"/>')
    pts = " ".join(f"{X0+s},{f(sig(s))}" for s in range(0, 2 * P + 1, 2))
    d.add(f'<g clip-path="url(#sc)"><polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.3" '
          f'stroke-linejoin="round"><animateTransform attributeName="transform" type="translate" '
          f'from="0 0" to="-{P} 0" dur="{T}s" repeatCount="indefinite"/></polyline></g>')
    d.add(f'<line x1="{X0}" y1="{thresh}" x2="{X0+SW}" y2="{thresh}" stroke="{PINK}" stroke-width="1" '
          f'stroke-dasharray="5 5"/>')
    d.add(d.text(X0, thresh - 8, "when X", "plex", 11, PINK))

    NOW = 440
    nx = X0 + NOW
    trig = sorted(((c - NOW) % P) * T / P for c, _ in spikes)
    kt, op = ["0"], ["0.4"]
    for t in trig:
        kt += [f(t / T), f((t + 0.05) / T), f((t + 0.7) / T)]
        op += ["0.4", "1", "0.4"]
    d.add(f'<line x1="{nx}" y1="28" x2="{nx}" y2="{base+14}" stroke="{PINK}" stroke-width="1" opacity="0.4">'
          f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
          f'keyTimes="{";".join(kt)};1" values="{";".join(op)};0.4"/></line>')
    cys = [f(sig(NOW + P * k / 600)) for k in range(601)]
    d.add(f'<circle cx="{nx}" cy="{cys[0]}" r="3" fill="{PINK}"><animate attributeName="cy" dur="{T}s" '
          f'repeatCount="indefinite" values="{";".join(cys)}"/></circle>')

    # log
    ly = 172
    logs = [("training crashed ", "call()"),
            ("out of the queue ", "whatsapp()"),
            ("download finished", "telegram()")]
    for i, (t, (what, act)) in enumerate(zip(trig, logs)):
        typed(d, f"lg{i}", X0, ly + 24 + i * 22,
              [("[trigger] ", PINK), (what, INK), ("  -> ", MUTED), (act, INK)],
              12.5, t + 0.05, T - 0.3, T, cps=70)
    return d.render()


# --------------------------------------------------------------------------- periodic table
def periodic():
    LANG, AI, APP, INFRA, SCI = PINK, CYAN, ORANGE, LIME, PURPLE
    els = [
        ("Ts", "TypeScript", LANG), ("Rs", "Rust", LANG),
        ("Py", "Python", LANG), ("Jl", "Julia", LANG),
        ("Ll", "llama.cpp", AI), ("Pt", "PyTorch", AI), ("Tf", "Transformers.js", AI), ("Wh", "Whisper", AI),
        ("Sw", "Swift", LANG), ("Kt", "Kotlin", LANG),
        ("Mc", "MCP", AI), ("Pw", "Playwright", AI, APP), ("Ta", "Tauri", APP),
        ("Ws", "WebSockets", APP),
        ("C", "C", LANG), ("Rd", "Redis", APP), ("St", "Stripe", APP), ("Dk", "Docker", INFRA),
        ("Cf", "Cloudflare", INFRA), ("Aw", "AWS", INFRA), ("Lx", "Linux", INFRA),
        ("Qk", "Qiskit", SCI), ("Np", "NumPy", SCI), ("Mn", "Manim", SCI), ("Tx", "LaTeX", SCI),
    ]
    # the "atomic mass" line: which parts of a platform I actually use
    DETAIL = {"Cf": "R2·Workers·AI", "Aw": "Bedrock·EC2", "Lx": "Arch·Ubuntu", "Ta": "iOS·Android·Desktop"}
    slots = [(0, 0), (0, 10)]
    for r in (1, 2):
        slots += [(r, 0), (r, 1)] + [(r, c) for c in range(7, 11)]
    slots += [(3, c) for c in range(11)]
    assert len(slots) == len(els)

    S, G = 78, 8
    X0 = (1000 - (11 * S + 10 * G)) / 2
    Y0 = 28
    d = Doc(1000, int(Y0 * 2 + 4 * S + 3 * G))
    paper(d)
    period = len(els) * 0.3 + 3
    for i, (el, (r, c)) in enumerate(zip(els, slots)):
        sym, name, color = el[:3]
        x, y = X0 + c * (S + G), Y0 + r * (S + G)
        if len(el) > 3:  # second category: marked top-right, like the legend swatches
            d.add(f'<rect x="{f(x+S-15)}" y="{y+7}" width="8" height="8" fill="{el[3]}"/>')
        fit = ' textLength="64" lengthAdjust="spacingAndGlyphs"' if width(name, "rc", 10.5) > 64 else ""
        d.add(f'<g><rect class="el" style="--c:{color};animation-delay:{f(i*0.3)}s" x="{f(x)}" y="{y}" '
              f'width="{S}" height="{S}" rx="2" fill="none" stroke="{RULE}"/>'
              + d.text(x + 7, y + 15, str(i + 1), "plex", 10, color)
              + d.text(x + S / 2, y + 46, sym, "rc-bold", 27, INK, "middle")
              + d.text(x + S / 2, y + 61, name, "rc", 10.5, MUTED, "middle", fit)
              + (d.text(x + S / 2, y + 72, DETAIL[sym], "rc", 8.5, INK, "middle") if sym in DETAIL else "")
              + "</g>")
    tx = X0 + (S + G) + 26
    d.add(d.text(tx, Y0 + 36, "The Periodic Table of Roy", "cmu-it", 28, INK))
    d.add(d.text(tx, Y0 + 60, "# reactive with coffee", "plex", 11.5, MUTED))
    lx, ly = X0 + 2 * (S + G) + 26, Y0 + (S + G) + 20
    for i, (name, color) in enumerate([("Languages", LANG), ("AI & inference", AI), ("App & backend", APP),
                                       ("Infra & Cloud", INFRA), ("Science", SCI)]):
        yy = ly + i * 25
        d.add(f'<rect x="{f(lx)}" y="{yy-9}" width="9" height="9" fill="{color}"/>')
        d.add(d.text(lx + 20, yy, name, "rc", 13.5, INK))
    d.css.append(f".el{{animation:ex {f(period)}s ease-in-out infinite}}"
                 f"@keyframes ex{{0%,9%,100%{{stroke:{RULE}}}3%{{stroke:var(--c);stroke-width:1.6px}}}}")
    return d.render()


# --------------------------------------------------------------------------- footer
def footer():
    d = Doc(1000, 104)
    paper(d)
    m, _ = d.math(500, 62, [("P", "cmu-it"), ("(hire) = |", "cmu-rm"), "<", ("Roy", "cmu-it"), ("|", "cmu-rm"),
                            ("your team", "cmu-it"), ">", ("|² → 1", "cmu-rm")], 32)
    d.add(m)
    return d.render()


# --------------------------------------------------------------------------- CV-style section headings
def heading(title, color, dark):
    size = 30
    w = width(title, "rc-bold", size)
    d = Doc(int(w + 4), 42)
    rest = "#d8d8d8" if dark else INK
    d.used.setdefault("rc-bold", set()).update(title)
    d.add(f'<text x="0" y="32" font-family="\'rc-bold\',{FALLBACK["rc-bold"]}" font-size="{size}">'
          f'<tspan fill="{color}">{esc(title[:3])}</tspan><tspan fill="{rest}">{esc(title[3:])}</tspan></text>')
    return d.render()


HEADINGS = [("Summary", CYAN), ("Experience", PINK), ("Research", ORANGE),
            ("Tech Stack", PURPLE), ("Selected Projects", LIME), ("Education", PURPLE)]

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, fn in [("header", header), ("bloch", bloch), ("observer", observer),
                     ("periodic", periodic), ("footer", footer)]:
        (OUT / f"{name}.svg").write_text(fn())
    for title, color in HEADINGS:
        slug = title.lower().replace(" ", "-")
        for dark in (False, True):
            (OUT / f"h-{slug}{'-dark' if dark else ''}.svg").write_text(heading(title, color, dark))
    for p in sorted(OUT.glob("*.svg")):
        print(f"{p.stat().st_size/1024:6.1f} KB  {p.name}")
