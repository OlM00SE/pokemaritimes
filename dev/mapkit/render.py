"""Rendering with inspection overlays.

Overlays (combine freely):
  grid       5-tile grid with coordinates
  collision  red hatch on blocks with collision bits set
  elevation  elevation digit per block, coloured by level (15 = bridge, 0 = transition)
  behavior   tall grass (green), surfable (blue), ledges (white arrow: the jump direction),
             encounter water
  events     warps W#, people P, trainers Tr, triggers T, signs S, hidden items H, with elevation
             where non-zero; given the checker's detail, trainers' sight (red) and the tiles
             each event is triggered from (cyan tick pointing at it)
  traps      one-way traps from the checker: magenta = can be entered but never left,
             orange = can only be left with Surf. Needs `detail` from checks.check_map.
"""
from PIL import Image, ImageDraw
from .project import TILE_FLAG_HAS_ENCOUNTERS, TILE_FLAG_SURFABLE
from .engine import DIRS
from .events import is_trainer

ELEV_COLORS = {0: (255, 255, 255), 1: (80, 160, 255), 3: (255, 255, 120), 4: (255, 170, 60),
               5: (255, 110, 110), 15: (220, 120, 255)}


class MetatileRenderer:
    def __init__(self, tiles):
        self.t = tiles
        self.cache = {}

    def metatile(self, mid, layers=(0, 1)):
        key = (mid, layers)
        if key in self.cache:
            return self.cache[key]
        backdrop = self.t.palette(0)[0]
        im = Image.new("RGB", (16, 16), backdrop)
        entries = self.t.entries(mid)
        if entries is None:
            ImageDraw.Draw(im).rectangle((0, 0, 15, 15), fill=(255, 0, 255))  # missing metatile
        else:
            px = im.load()
            for layer in layers:
                for q in range(4):
                    e = entries[layer * 4 + q]
                    src = self.t.tile(e & 0x3FF)
                    if src is None:
                        continue
                    hf, vf, colors = (e >> 10) & 1, (e >> 11) & 1, self.t.palette(e >> 12)
                    ox, oy = (q % 2) * 8, (q // 2) * 8
                    for i, c in enumerate(src):
                        if c:
                            xx, yy = i % 8, i // 8
                            px[ox + (7 - xx if hf else xx), oy + (7 - yy if vf else yy)] = colors[c]
        self.cache[key] = im
        return im


def render_layout(project, layout, scale=1, overlays=(), mapdata=None, detail=None):
    tiles = layout.tiles
    mr = MetatileRenderer(tiles)
    w, h = layout.width, layout.height
    img = Image.new("RGB", (w * 16, h * 16))
    for y in range(h):
        for x in range(w):
            img.paste(mr.metatile(layout.mid(x, y)), (x * 16, y * 16))
    if scale != 1:
        img = img.resize((w * 16 * scale, h * 16 * scale), Image.NEAREST)
    if overlays:
        # detail: the checker's findings (checks.check_map(..., detail=d)); 'traps' draws them
        draw_overlays(project, img, layout, 16 * scale, overlays, mapdata, detail or {})
    return img


def _arrow(d, x0, y0, s, direction):
    """A filled triangle pointing the way a ledge jumps, outlined so it reads on any tile."""
    c, a, b = s / 2, s * 0.22, s * 0.78
    pts = {"S": [(x0 + a, y0 + a), (x0 + b, y0 + a), (x0 + c, y0 + b)],
           "N": [(x0 + a, y0 + b), (x0 + b, y0 + b), (x0 + c, y0 + a)],
           "E": [(x0 + a, y0 + a), (x0 + a, y0 + b), (x0 + b, y0 + c)],
           "W": [(x0 + b, y0 + a), (x0 + b, y0 + b), (x0 + a, y0 + c)]}[direction]
    d.polygon(pts, fill=(255, 255, 255, 230), outline=(0, 0, 0, 255))


def draw_overlays(project, img, layout, s, overlays, mapdata, detail=None):
    d = ImageDraw.Draw(img, "RGBA")
    w, h = layout.width, layout.height
    tiles = layout.tiles
    detail = detail or {}
    jumps = {project.mb(n): a for n, a in (("MB_JUMP_SOUTH", "S"), ("MB_JUMP_NORTH", "N"),
                                          ("MB_JUMP_EAST", "E"), ("MB_JUMP_WEST", "W"))}
    for y in range(h):
        for x in range(w):
            x0, y0 = x * s, y * s
            if "traps" in overlays:
                if (x, y) in detail.get("trapped", ()):
                    d.rectangle((x0, y0, x0 + s - 1, y0 + s - 1), fill=(255, 0, 255, 120))
                elif (x, y) in detail.get("needs_surf", ()):
                    d.rectangle((x0, y0, x0 + s - 1, y0 + s - 1), fill=(255, 150, 0, 110))
            if "collision" in overlays and layout.coll(x, y):
                d.rectangle((x0, y0, x0 + s - 1, y0 + s - 1), fill=(255, 0, 0, 70))
                d.line((x0, y0, x0 + s - 1, y0 + s - 1), fill=(255, 0, 0, 140))
            if "behavior" in overlays:
                b = tiles.behavior(layout.mid(x, y))
                fl = project.tile_flags.get(b, 0)
                if fl & TILE_FLAG_SURFABLE:
                    d.rectangle((x0 + 2, y0 + 2, x0 + s - 3, y0 + s - 3), outline=(0, 90, 255, 200))
                elif fl & TILE_FLAG_HAS_ENCOUNTERS:
                    d.rectangle((x0 + 2, y0 + 2, x0 + s - 3, y0 + s - 3), outline=(0, 200, 0, 220))
                if b in jumps:
                    _arrow(d, x0, y0, s, jumps[b])
            if "elevation" in overlays:
                e = layout.elev(x, y)
                d.text((x0 + 2, y0 + 1), f"{e:X}", fill=ELEV_COLORS.get(e, (200, 200, 200)) + (255,))
    if "grid" in overlays:
        for x in range(0, w, 5):
            d.line([(x * s, 0), (x * s, h * s)], fill=(0, 0, 0, 120))
            d.text((x * s + 2, 1), str(x), fill=(255, 255, 0))
        for y in range(0, h, 5):
            d.line([(0, y * s), (w * s, y * s)], fill=(0, 0, 0, 120))
            d.text((2, y * s + 2), str(y), fill=(255, 255, 0))
    if "events" in overlays and mapdata is not None:
        # from the checker (mapkit/events.py): trainers' sight, and where each event triggers
        for lines in detail.get("sight", {}).values():
            for tiles in lines.values():
                for x, y in tiles:
                    d.rectangle((x * s, y * s, x * s + s - 1, y * s + s - 1), fill=(255, 60, 0, 90))
        for (kind, i), spots in detail.get("spots", {}).items():
            for x, y, f in spots:
                cx, cy = x * s + s / 2, y * s + s / 2
                dx, dy = DIRS[f]
                d.line((cx, cy, cx + dx * s * 0.45, cy + dy * s * 0.45), fill=(0, 230, 255, 255), width=2)
                d.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=(0, 230, 255, 255))

        def mark(ev, color, label):
            x0, y0 = ev["x"] * s, ev["y"] * s
            d.rectangle((x0 + 1, y0 + 1, x0 + s - 2, y0 + s - 2), outline=color, width=2)
            el = ev.get("elevation", 0)
            d.text((x0 + 3, y0 + 3), label + (f"@{el}" if el else ""), fill=color)
        for i, e in enumerate(mapdata.events("warp_events")):
            mark(e, (255, 40, 40, 255), f"W{i}")
        for e in mapdata.events("object_events"):
            trainer = is_trainer(e)
            mark(e, (255, 90, 40, 255) if trainer else (40, 140, 255, 255), "Tr" if trainer else "P")
        for e in mapdata.events("coord_events"):
            mark(e, (255, 160, 0, 255), "T")
        for e in mapdata.events("bg_events"):
            mark(e, (190, 60, 255, 255), "H" if e.get("type") == "hidden_item" else "S")


def render_map(project, name, scale=1, overlays=(), crop=None, detail=None):
    """crop: (x0, y0, x1, y1) in tiles, inclusive, to render part of a big map.
    detail: checker findings for the 'traps' overlay (see render_layout)."""
    m = project.load_map(name)
    img = render_layout(project, m.layout, scale, overlays, m, detail)
    if crop:
        s = 16 * scale
        x0, y0, x1, y1 = crop
        img = img.crop((x0 * s, y0 * s, (x1 + 1) * s, (y1 + 1) * s))
    return img


def changed_cells(layout, old_blocks):
    """Cells whose block (metatile, collision or elevation) differs from old_blocks."""
    w = layout.width
    return [(i % w, i // w) for i, (a, b) in enumerate(zip(old_blocks, layout.blocks)) if a != b]


def render_diff(project, layout, old_blocks, scale=2, margin=2):
    """Before | after, cropped to the changed area (plus a margin), changed cells outlined.
    Returns (image, changed cells), or (None, []) when nothing changed."""
    cells = changed_cells(layout, old_blocks)
    if not cells:
        return None, []
    new_blocks = layout.blocks
    layout.blocks = list(old_blocks)
    try:
        before = render_layout(project, layout, 1)
    finally:
        layout.blocks = new_blocks
    after = render_layout(project, layout, 1)
    s = 16 * scale
    x0 = max(0, min(x for x, _ in cells) - margin); x1 = min(layout.width - 1, max(x for x, _ in cells) + margin)
    y0 = max(0, min(y for _, y in cells) - margin); y1 = min(layout.height - 1, max(y for _, y in cells) + margin)
    box = (x0 * 16, y0 * 16, (x1 + 1) * 16, (y1 + 1) * 16)
    size = ((x1 - x0 + 1) * s, (y1 - y0 + 1) * s)          # upscale only the cropped change
    before, after = (im.crop(box).resize(size, Image.NEAREST) for im in (before, after))
    for im in (before, after):
        d = ImageDraw.Draw(im, "RGBA")
        for x, y in cells:
            px, py = (x - x0) * s, (y - y0) * s
            d.rectangle((px, py, px + s - 1, py + s - 1), outline=(255, 0, 255, 200))
    gap, head = 8, 14
    out = Image.new("RGB", (before.width * 2 + gap, before.height + head), (24, 24, 32))
    d = ImageDraw.Draw(out)
    d.text((2, 1), f"before   (tiles {x0},{y0} to {x1},{y1}; {len(cells)} changed cells outlined)",
           fill=(255, 255, 0))
    d.text((before.width + gap + 2, 1), "after", fill=(255, 255, 0))
    out.paste(before, (0, head)); out.paste(after, (before.width + gap, head))
    return out, cells


def render_sheet(project, primary, secondary, start=0, count=None, cols=16, cell=32):
    """Labeled metatile index: hex id of each row on the left, low nibble above each cell."""
    tiles = project.tileset_pair(primary, secondary)
    mr = MetatileRenderer(tiles)
    ids = [i for i in tiles.metatile_ids() if i >= start][:count]
    rows = (len(ids) + cols - 1) // cols
    lab = 12
    img = Image.new("RGB", (cols * cell + 30, rows * (cell + lab)), (40, 40, 40))
    d = ImageDraw.Draw(img)
    for n, mid in enumerate(ids):
        cx, cy = 30 + (n % cols) * cell, (n // cols) * (cell + lab)
        if n % cols == 0:
            d.text((1, cy + 14), f"{mid:03X}", fill=(255, 255, 0))
        d.text((cx + 10, cy), f"{mid & 0xF:X}", fill=(190, 190, 190))
        img.paste(mr.metatile(mid).resize((cell - 2, cell - 2), Image.NEAREST), (cx, cy + lab))
    return img


EDGE_DIRECTIONS = ("up", "down", "left", "right")      # dive / emerge aren't edge connections


def neighbour_origin(c, w, h, other):
    """Top-left tile of a neighbour connected by `c`, relative to a w x h map, or None for a
    connection that isn't an edge (dive, emerge)."""
    if c["direction"] not in EDGE_DIRECTIONS:
        return None
    o = c["offset"]
    return {"up": (o, -other.height), "down": (o, h), "left": (-other.width, o),
            "right": (w, o)}[c["direction"]]


def render_contexts(project, name, layouts, margin=8, scale=1, dim=0.45):
    """For each layout in `layouts` (versions of the map, e.g. before and after an edit): that
    layout plus a `margin`-tile strip of each directly connected neighbour, as the player sees
    it walking across a seam. Neighbours are dimmed (`dim` = how much grey is blended in) and
    the map's own outline is drawn, so seams can be judged at a glance. The neighbours are
    rendered once and shared."""
    m = project.load_map(name)
    w, h = layouts[0].width, layouts[0].height
    x0, y0, x1, y1 = -margin, -margin, w + margin, h + margin     # canvas, in the map's tiles
    base = Image.new("RGB", ((x1 - x0) * 16, (y1 - y0) * 16), (24, 24, 32))
    for c in m.connections:
        other = project.const_to_map.get(c["map"])
        if not other:
            continue
        ol = project.load_map(other).layout
        origin = neighbour_origin(c, w, h, ol)
        if origin is None:
            continue
        img = render_layout(project, ol, 1)
        if dim:
            img = Image.blend(img, Image.new("RGB", img.size, (40, 40, 48)), dim)
        base.paste(img, ((origin[0] - x0) * 16, (origin[1] - y0) * 16))
    out = []
    for lay in layouts:
        canvas = base.copy()
        canvas.paste(render_layout(project, lay, 1), (-x0 * 16, -y0 * 16))
        d = ImageDraw.Draw(canvas)
        d.rectangle((-x0 * 16 - 1, -y0 * 16 - 1, (w - x0) * 16, (h - y0) * 16), outline=(255, 255, 255))
        if scale != 1:
            canvas = canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)
        out.append(canvas)
    return out


def render_context(project, name, margin=8, scale=1, layout=None, dim=0.45):
    """The map (or `layout`, e.g. a preview) with its neighbours' edges; see render_contexts."""
    return render_contexts(project, name, [layout or project.load_map(name).layout], margin, scale, dim)[0]


def render_world(project, start, shrink=2):
    """Stitch every map reachable through connections from `start`."""
    pos, size, queue = {start: (0, 0)}, {}, [start]
    while queue:
        name = queue.pop(0)
        m = project.load_map(name)
        size[name] = (m.layout.width, m.layout.height)
        for c in m.connections:
            other = project.const_to_map.get(c["map"])
            if not other or other in pos:
                continue
            ol = project.load_map(other).layout
            origin = neighbour_origin(c, *size[name], ol)
            if origin is None:
                continue
            pos[other] = (pos[name][0] + origin[0], pos[name][1] + origin[1])
            queue.append(other)
    minx = min(p[0] for p in pos.values()); miny = min(p[1] for p in pos.values())
    maxx = max(pos[n][0] + size[n][0] for n in pos); maxy = max(pos[n][1] + size[n][1] for n in pos)
    world = Image.new("RGB", ((maxx - minx) * 16 // shrink, (maxy - miny) * 16 // shrink), (24, 24, 32))
    d = ImageDraw.Draw(world)
    for name, (x, y) in pos.items():
        img = render_map(project, name)
        if shrink > 1:
            img = img.resize((img.width // shrink, img.height // shrink), Image.LANCZOS)
        px, py = (x - minx) * 16 // shrink, (y - miny) * 16 // shrink
        world.paste(img, (px, py))
        d.rectangle((px, py, px + img.width - 1, py + img.height - 1), outline=(255, 255, 255))
        d.rectangle((px + 2, py + 2, px + 8 + 6 * len(name), py + 14), fill=(0, 0, 0))
        d.text((px + 5, py + 3), name, fill=(255, 255, 0))
    return world, pos
