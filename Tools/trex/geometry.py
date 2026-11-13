"""Procedural T-Rex part geometry (Blender units = metres, Z up, head toward -Y)."""
import math

import bmesh
import bpy
from mathutils import Vector

# Loft profiles: (y, z_top, z_bottom, half_width). Interpolated with Catmull-Rom.
BODY_PROFILE = [
    (1.10, 4.30, 3.38, 0.62),
    (0.40, 4.46, 2.98, 0.82),
    (-0.30, 4.48, 2.60, 0.96),
    (-1.10, 4.40, 2.22, 1.06),
    (-1.90, 4.30, 2.12, 1.04),
    (-2.60, 4.22, 2.30, 0.92),
    (-3.15, 4.24, 2.70, 0.76),
    (-3.60, 4.48, 3.12, 0.64),
    (-3.98, 4.82, 3.48, 0.58),
    (-4.34, 5.10, 3.76, 0.55),
    (-4.62, 5.22, 3.90, 0.52),
]
TAIL_PROFILE = [
    (0.30, 4.46, 2.96, 0.74),
    (1.20, 4.36, 3.20, 0.62),
    (2.20, 4.16, 3.38, 0.48),
    (3.20, 3.96, 3.43, 0.35),
    (4.20, 3.75, 3.39, 0.25),
    (5.20, 3.52, 3.27, 0.155),
    (6.20, 3.28, 3.14, 0.08),
    (6.90, 3.13, 3.06, 0.035),
]
HEAD_PROFILE = [
    (-4.30, 5.30, 3.98, 0.56),
    (-4.60, 5.46, 4.02, 0.67),
    (-4.90, 5.48, 4.10, 0.63),
    (-5.20, 5.26, 4.18, 0.51),
    (-5.50, 5.05, 4.23, 0.41),
    (-5.80, 4.89, 4.26, 0.35),
    (-6.05, 4.76, 4.28, 0.31),
    (-6.20, 4.60, 4.30, 0.27),
]
JAW_PROFILE = [
    (-4.35, 4.30, 3.62, 0.55),
    (-4.75, 4.27, 3.76, 0.55),
    (-5.15, 4.26, 3.90, 0.46),
    (-5.55, 4.27, 4.00, 0.37),
    (-5.95, 4.28, 4.07, 0.30),
    (-6.12, 4.28, 4.12, 0.26),
]
UPPER_LIP_Z = 4.27
LOWER_LIP_Z = 4.26
EYE_Y, EYE_Z = -4.98, 5.02
# The head parts are modelled at a base size, then enlarged about the neck joint.
HEAD_PIVOT = (0.0, -4.40, 4.45)
HEAD_SCALE = 1.22
HEAD_PARTS = ("Head", "LowerJaw", "UpperTeeth", "LowerTeeth", "LeftEye", "RightEye", "Tongue")


def head_point(p):
    """Map a point of the base-size head to its scaled position."""
    return tuple(c + (v - c) * HEAD_SCALE for v, c in zip(p, HEAD_PIVOT))


def catmull(points, t):
    """Catmull-Rom through a list of tuples at parameter t in [0, len-1]."""
    n = len(points)
    i = min(int(t), n - 2)
    f = t - i
    p0 = points[max(i - 1, 0)]
    p1, p2 = points[i], points[i + 1]
    p3 = points[min(i + 2, n - 1)]
    out = []
    for a, b, c, d in zip(p0, p1, p2, p3):
        out.append(0.5 * ((2 * b) + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f
                          + (-a + 3 * b - 3 * c + d) * f ** 3))
    return out


def superellipse(angle, exponent):
    c, s = math.cos(angle), math.sin(angle)
    return (math.copysign(abs(c) ** (2 / exponent), c), math.copysign(abs(s) ** (2 / exponent), s))


def loft(name, profile, rows, ring=40, exponent=2.3, cap_front=True, cap_back=True,
         shape=None, cap_rows=5):
    """Build a closed tube through the profile. shape(x, y, z, u, angle) may displace verts."""
    samples = [catmull(profile, t * (len(profile) - 1) / (rows - 1)) for t in range(rows)]
    bm = bmesh.new()
    rings = []

    def add_ring(y, top, bottom, half_w, scale=1.0, u=0.0):
        zc, hh = (top + bottom) / 2, (top - bottom) / 2
        verts = []
        for k in range(ring):
            angle = 2 * math.pi * k / ring
            sx, sz = superellipse(angle, exponent)
            # Rounder belly, flatter back.
            hz = hh * scale * (1.0 if sz > 0 else 1.04)
            x, z = sx * half_w * scale, zc + sz * hz
            if shape:
                x, y2, z = shape(x, y, z, u, angle)
            else:
                y2 = y
            verts.append(bm.verts.new((x, y2, z)))
        rings.append(verts)

    def cap(sample, direction, reverse):
        y, top, bottom, half_w = sample
        span = abs(samples[1][0] - samples[0][0]) * 2.2 if direction < 0 else abs(samples[-1][0] - samples[-2][0]) * 2.2
        span = max(span, half_w * 0.9)
        for c in range(1, cap_rows):
            a = (c / cap_rows) * math.pi / 2
            add_ring(y + direction * span * math.sin(a) * 0.55, top, bottom, half_w, math.cos(a))
        tip = bm.verts.new((0.0, y + direction * span * 0.55, (top + bottom) / 2))
        return tip

    front_tip = back_tip = None
    if cap_front:
        front_tip = cap(samples[0], 1 if samples[0][0] > samples[-1][0] else -1, False)
        rings.reverse()
    for idx, s in enumerate(samples):
        add_ring(*s, u=idx / (rows - 1))
    if cap_back:
        back_start = len(rings)
        back_tip = cap(samples[-1], 1 if samples[-1][0] > samples[0][0] else -1, True)

    for a, b in zip(rings, rings[1:]):
        for k in range(ring):
            bm.faces.new((a[k], a[(k + 1) % ring], b[(k + 1) % ring], b[k]))
    if front_tip:
        r = rings[0]
        for k in range(ring):
            bm.faces.new((front_tip, r[(k + 1) % ring], r[k]))
    if back_tip:
        r = rings[-1]
        for k in range(ring):
            bm.faces.new((back_tip, r[k], r[(k + 1) % ring]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish(name, bm)


def finish(name, bm, subdivide=1):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if subdivide:
        mod = obj.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = mod.render_levels = subdivide
        apply_modifiers(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def apply_modifiers(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated)
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    bpy.data.meshes.remove(old)
    mesh.name = obj.name


def skin_chain(name, nodes, edges, subdivide=2):
    """nodes: list of (xyz, (rx, ry)); edges: index pairs. Uses the Skin modifier."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([n[0] for n in nodes], edges, [])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    skin = obj.modifiers.new("Skin", "SKIN")
    skin.use_smooth_shade = True
    skin.branch_smoothing = 0.6
    data = mesh.skin_vertices[0].data
    for i, (_, radius) in enumerate(nodes):
        data[i].radius = radius
        data[i].use_root = i == 0
    sub = obj.modifiers.new("Subsurf", "SUBSURF")
    sub.levels = sub.render_levels = subdivide
    apply_modifiers(obj)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def cone(bm, base, direction, radius, length, segments=8, curve=Vector((0, 0, 0))):
    """Add a slightly curved claw/tooth cone to bm."""
    direction = direction.normalized()
    side = direction.cross(Vector((0, 0, 1)))
    if side.length < 1e-3:
        side = direction.cross(Vector((1, 0, 0)))
    side.normalize()
    up = side.cross(direction).normalized()
    levels = 4
    rings = []
    for lv in range(levels):
        t = lv / levels
        center = base + direction * (length * t) + curve * (t * t)
        r = radius * (1 - t) ** 0.8
        rings.append([bm.verts.new(center + (side * math.cos(a) + up * math.sin(a)) * r)
                      for a in (2 * math.pi * k / segments for k in range(segments))])
    tip = bm.verts.new(base + direction * length + curve)
    for a, b in zip(rings, rings[1:]):
        for k in range(segments):
            bm.faces.new((a[k], a[(k + 1) % segments], b[(k + 1) % segments], b[k]))
    bottom = rings[0]
    hub = bm.verts.new(base)
    for k in range(segments):
        bm.faces.new((bottom[(k + 1) % segments], bottom[k], hub))
    for k in range(segments):
        bm.faces.new((rings[-1][k], rings[-1][(k + 1) % segments], tip))


def profile_at(profile, y):
    """Linear lookup of a profile value at y."""
    pts = sorted(profile, key=lambda p: p[0])
    if y <= pts[0][0]:
        return pts[0]
    for a, b in zip(pts, pts[1:]):
        if a[0] <= y <= b[0]:
            f = (y - a[0]) / (b[0] - a[0])
            return tuple(x + (z - x) * f for x, z in zip(a, b))
    return pts[-1]


def surface_x(profile, y, z, exponent):
    """Half-width of a superellipse loft section at height z."""
    _, top, bottom, w = profile_at(profile, y)
    zc, hh = (top + bottom) / 2, (top - bottom) / 2
    sz = max(-0.999, min(0.999, (z - zc) / hh))
    # z = sign(s)|s|^(2/e) -> |sin| = |sz|^(e/2); x = |cos|^(2/e)
    sin_a = abs(sz) ** (exponent / 2)
    return w * (1 - sin_a * sin_a) ** (1 / exponent)


def head_shape(x, y, z, u, angle):
    """Skull details: brow bosses, cheek flare, slight snout taper and nasal ridge."""
    # Lacrimal / postorbital bosses above and in front of the eye.
    for by, bz, bx, amp, rad in ((-5.06, 5.22, 0.42, 0.08, 0.15), (-4.80, 5.30, 0.46, 0.06, 0.15)):
        d = math.dist((abs(x), y, z), (bx, by, bz))
        if d < rad * 2.5:
            k = math.exp(-(d / rad) ** 2) * amp
            x += math.copysign(k * 0.6, x)
            z += k
    # Eye socket recess.
    d = math.dist((abs(x), y, z), (surface_x(HEAD_PROFILE, EYE_Y, EYE_Z, 2.9), EYE_Y, EYE_Z))
    x -= math.copysign(math.exp(-(d / 0.10) ** 2) * 0.03, x)
    # Nasal ridge: flatten the top centre slightly, ridge bumps along snout.
    if z > 4.5 and y < -5.2:
        z += 0.012 * math.sin(y * 28) * math.exp(-(x / 0.12) ** 2)
    return x, y, z


def jaw_shape(x, y, z, u, angle):
    # Chin bulge underneath the dentary, muscle bulge at the back.
    if z < 4.1:
        z -= 0.04 * math.exp(-((y + 4.6) / 0.25) ** 2)
    return x, y, z


def body_shape(x, y, z, u, angle):
    # Pectoral area & slight dorsal ridge.
    if z > 3.9:
        z += 0.04 * math.exp(-(x / 0.18) ** 2)
    return x, y, z


def build_body():
    return loft("Body", BODY_PROFILE, rows=46, ring=44, exponent=2.25, shape=body_shape, cap_rows=4)


def build_tail():
    return loft("Tail", TAIL_PROFILE, rows=56, ring=36, exponent=2.4, cap_rows=4)


def build_head():
    return loft("Head", HEAD_PROFILE, rows=40, ring=44, exponent=2.9, shape=head_shape, cap_rows=5)


def build_jaw():
    return loft("LowerJaw", JAW_PROFILE, rows=32, ring=36, exponent=3.0, shape=jaw_shape, cap_rows=5)


def leg_nodes(side):
    s = 1 if side == "L" else -1
    x = 0.80 * s
    nodes = [
        ((0.72 * s, 0.10, 3.50), (0.74, 0.95)),   # 0 hip / thigh top
        ((0.84 * s, -0.25, 2.80), (0.70, 0.82)),  # 1 thigh belly
        ((0.88 * s, -0.62, 2.05), (0.40, 0.44)),  # 2 knee
        ((0.88 * s, -0.20, 1.40), (0.31, 0.34)),  # 3 shin
        ((0.86 * s, 0.25, 0.80), (0.19, 0.21)),   # 4 ankle
        ((0.86 * s, 0.08, 0.48), (0.14, 0.15)),   # 5 metatarsal
        ((0.86 * s, -0.08, 0.20), (0.17, 0.15)),  # 6 ball
        ((x + 0.0 * s, -0.55, 0.12), (0.10, 0.09)),  # 7 middle toe mid
        ((x + 0.0 * s, -0.92, 0.07), (0.06, 0.05)),  # 8 middle toe tip
        ((x - 0.18 * s, -0.42, 0.12), (0.09, 0.08)),  # 9 inner toe mid
        ((x - 0.28 * s, -0.72, 0.07), (0.05, 0.045)),  # 10 inner toe tip
        ((x + 0.18 * s, -0.42, 0.12), (0.09, 0.08)),  # 11 outer toe mid
        ((x + 0.28 * s, -0.72, 0.07), (0.05, 0.045)),  # 12 outer toe tip
    ]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (6, 9), (9, 10), (6, 11), (11, 12)]
    return nodes, edges


def build_leg(side):
    nodes, edges = leg_nodes(side)
    obj = skin_chain(("LeftLeg" if side == "L" else "RightLeg"), nodes, edges)
    # Claws as extra islands in the same part (material index 1 = keratin).
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    skin_faces = len(bm.faces)
    for mid, tip in ((7, 8), (9, 10), (11, 12)):
        a, b = Vector(nodes[mid][0]), Vector(nodes[tip][0])
        direction = (b - a).normalized()
        cone(bm, b - direction * 0.03, direction, 0.05, 0.20, curve=Vector((0, 0, -0.06)))
    bm.faces.ensure_lookup_table()
    for f in bm.faces[skin_faces:]:
        f.material_index = 1
        f.smooth = True
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def build_arm(side):
    s = 1 if side == "L" else -1
    nodes = [
        ((0.58 * s, -2.86, 2.98), (0.17, 0.19)),
        ((0.66 * s, -3.10, 2.55), (0.12, 0.13)),
        ((0.66 * s, -3.42, 2.50), (0.085, 0.09)),
        ((0.63 * s, -3.62, 2.42), (0.06, 0.06)),
        ((0.66 * s, -3.80, 2.30), (0.035, 0.035)),
        ((0.58 * s, -3.78, 2.32), (0.033, 0.033)),
    ]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)]
    obj = skin_chain("LeftArm" if side == "L" else "RightArm", nodes, edges)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = len(bm.faces)
    for tip in (4, 5):
        a, b = Vector(nodes[3][0]), Vector(nodes[tip][0])
        d = (b - a).normalized()
        cone(bm, b - d * 0.01, d, 0.03, 0.10, curve=Vector((0, 0, -0.04)))
    bm.faces.ensure_lookup_table()
    for f in bm.faces[count:]:
        f.material_index = 1
        f.smooth = True
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def build_teeth(upper):
    bm = bmesh.new()
    if upper:
        ys = [-6.08, -6.00, -5.92] + [-5.80 + i * 0.105 for i in range(9)]
    else:
        ys = [-6.00, -5.91] + [-5.80 + i * 0.105 for i in range(8)]
    for side in (1, -1):
        for i, y in enumerate(ys):
            if upper:
                y_, top, bottom, w = profile_at(HEAD_PROFILE, y)
                base = Vector((side * (w - 0.075), y, UPPER_LIP_Z + 0.03))
                length = 0.10 + 0.10 * math.sin(min(i, 8) / 8 * math.pi * 0.9 + 0.3)
                if i < 3:
                    length *= 0.75
                direction = Vector((side * 0.06, 0.12, -1.0))
            else:
                y_, top, bottom, w = profile_at(JAW_PROFILE, y)
                base = Vector((side * (w - 0.11), y, LOWER_LIP_Z - 0.03))
                length = 0.08 + 0.08 * math.sin(min(i, 8) / 8 * math.pi * 0.9 + 0.3)
                direction = Vector((side * 0.04, 0.10, 1.0))
            radius = 0.022 + length * 0.17
            cone(bm, base, direction, radius, length, segments=8,
                 curve=Vector((0, 0.025, 0)))
    for f in bm.faces:
        f.smooth = True
    return finish("UpperTeeth" if upper else "LowerTeeth", bm, subdivide=0)


def build_eye(side):
    s = 1 if side == "L" else -1
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=14, radius=0.08,
                                         location=(s * (surface_x(HEAD_PROFILE, EYE_Y, EYE_Z, 2.9) - 0.035), EYE_Y, EYE_Z))
    obj = bpy.context.active_object
    obj.name = "LeftEye" if side == "L" else "RightEye"
    obj.data.name = obj.name
    # Point the +Z pole (pupil) outward and slightly forward/up.
    look = Vector((s * 1.0, -0.55, 0.15)).normalized()
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(look)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    loc = obj.location.copy()
    obj.location = (0, 0, 0)
    obj.data.transform(__import__("mathutils").Matrix.Translation(loc))
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def build_tongue():
    bm = bmesh.new()
    obj = None
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=10, radius=1.0)
    for v in bm.verts:
        v.co.x *= 0.20
        v.co.y *= 0.62
        v.co.z *= 0.06
        v.co += Vector((0.0, -5.0, 4.13))
    obj = finish("Tongue", bm, subdivide=0)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def assign_mouth_faces(head, jaw):
    """Mark the palate and the jaw's inner floor with material index 1 (mouth)."""
    for poly in head.data.polygons:
        c = poly.center
        if poly.normal.z < -0.55 and c.z < UPPER_LIP_Z + 0.08 and abs(c.x) < profile_at(HEAD_PROFILE, c.y)[3] - 0.06:
            poly.material_index = 1
    for poly in jaw.data.polygons:
        c = poly.center
        if poly.normal.z > 0.55 and abs(c.x) < profile_at(JAW_PROFILE, c.y)[3] - 0.06:
            poly.material_index = 1


def build_all():
    parts = {
        "Body": build_body(),
        "Tail": build_tail(),
        "Head": build_head(),
        "LowerJaw": build_jaw(),
        "LeftLeg": build_leg("L"),
        "RightLeg": build_leg("R"),
        "LeftArm": build_arm("L"),
        "RightArm": build_arm("R"),
        "UpperTeeth": build_teeth(True),
        "LowerTeeth": build_teeth(False),
        "LeftEye": build_eye("L"),
        "RightEye": build_eye("R"),
        "Tongue": build_tongue(),
    }
    assign_mouth_faces(parts["Head"], parts["LowerJaw"])
    from mathutils import Matrix
    pivot = Vector(HEAD_PIVOT)
    m = Matrix.Translation(pivot) @ Matrix.Scale(HEAD_SCALE, 4) @ Matrix.Translation(-pivot)
    for name in HEAD_PARTS:
        parts[name].data.transform(m)
    return parts
