"""Procedural T-Rex actions: in-place Walk/Run cycles, HeadShake, Roar (jaw open).

Poses are evaluated with a small FK solver in armature space, legs with analytic
two-bone IK so planted feet stay on the ground while the body moves in place.
"""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

FPS = 24
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

# Gait parameters (Blender metres). speed = excursion / (duty * period).
GAITS = {
    "Walk": {"period": 2.0, "duty": 0.62, "excursion": 2.0, "lift": 0.45, "crouch": 0.04, "bob": 0.07, "pitch": 2.0},
    "Run": {"period": 1.0, "duty": 0.42, "excursion": 2.5, "lift": 0.80, "crouch": 0.22, "bob": 0.12, "pitch": 7.0},
}


def gait_speed(name):
    g = GAITS[name]
    return g["excursion"] / (g["duty"] * g["period"])


def rot(axis, degrees):
    return Quaternion(axis, math.radians(degrees))


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Pose:
    """Per-frame pose: armature-space rotations (rest frame) per bone + root offset."""

    def __init__(self):
        self.rot = {}
        self.root_offset = Vector((0, 0, 0))
        self.feet = {}  # side -> (ball world pos, metatarsal angle deg, toe pitch deg)

    def add(self, bone, q):
        self.rot[bone] = q @ self.rot.get(bone, Quaternion())


class Solver:
    def __init__(self, rig):
        self.rig = rig
        self.bones = rig.data.bones
        self.order = [b.name for b in self._walk(b for b in self.bones if b.parent is None)]

    def _walk(self, roots):
        for b in roots:
            yield b
            yield from self._walk(b.children)

    def rel(self, bone):
        if bone.parent is None:
            return bone.matrix_local.copy()
        return bone.parent.matrix_local.inverted() @ bone.matrix_local

    def solve(self, pose):
        """Return {bone: basis matrix} for this pose."""
        world, basis = {}, {}
        for name in self.order:
            bone = self.bones[name]
            parent_world = world[bone.parent.name] if bone.parent else Matrix.Identity(4)
            base = parent_world @ self.rel(bone)
            if name.startswith(("Thigh_", "Shin_", "Foot_", "Toe_")):
                target = self.leg_target(name, base, pose, world)
                b = base.inverted() @ target
            else:
                rest_rot = bone.matrix_local.to_quaternion()
                q = pose.rot.get(name, Quaternion())
                local_q = rest_rot.inverted() @ q @ rest_rot
                b = local_q.to_matrix().to_4x4()
                if name == "Root":
                    b.translation = rest_rot.inverted() @ pose.root_offset
            basis[name] = b
            world[name] = base @ b
        return basis

    # --- legs -------------------------------------------------------------
    def leg_target(self, name, base, pose, world):
        part, side = name.split("_")
        if part == "Thigh":
            self._chain = self.leg_chain(side, base.translation, pose)
        start, end = self._chain[part]
        return align(base, start, end)

    def leg_chain(self, side, hip, pose):
        b = self.bones
        l1 = b[f"Thigh_{side}"].length
        l2 = b[f"Shin_{side}"].length
        l3 = b[f"Foot_{side}"].length
        l4 = b[f"Toe_{side}"].length
        ball, meta_deg, toe_deg = pose.feet[side]
        a = math.radians(meta_deg)
        ankle = ball + Vector((0, math.sin(a), math.cos(a))) * l3
        d_vec = ankle - hip
        d = min(d_vec.length, (l1 + l2) * 0.995)
        dn = d_vec.normalized()
        ankle = hip + dn * d
        cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
        ang = math.acos(max(-1.0, min(1.0, cos_a)))
        pole = Vector((0, -1, 0.15))
        n = (pole - dn * pole.dot(dn)).normalized()
        knee = hip + (dn * math.cos(ang) + n * math.sin(ang)) * l1
        ball = ankle + (ball - ankle).normalized() * l3
        t = math.radians(toe_deg)
        toe_rest = (Vector(self.bones[f"Toe_{side}"].tail_local) - Vector(self.bones[f"Toe_{side}"].head_local)).normalized()
        toe_dir = Quaternion(X, t) @ toe_rest
        return {
            "Thigh": (hip, knee),
            "Shin": (knee, ankle),
            "Foot": (ankle, ball),
            "Toe": (ball, ball + toe_dir * l4),
        }


def align(base, start, end):
    """Matrix with base's orientation rotated so its Y axis points start->end, located at start."""
    current = base.to_quaternion()
    y_axis = current @ Y
    q = y_axis.rotation_difference((end - start).normalized()) @ current
    m = q.to_matrix().to_4x4()
    m.translation = start
    return m


# --- pose builders -------------------------------------------------------
def rest_feet(rig):
    feet = {}
    for side in ("L", "R"):
        foot = rig.data.bones[f"Foot_{side}"]
        ball = Vector(foot.tail_local)
        v = Vector(foot.head_local) - ball
        feet[side] = (ball, math.degrees(math.atan2(v.y, v.z)), 0.0)
    return feet


def gait_foot(rest, phase, g):
    ball0, meta0, _ = rest
    duty, e = g["duty"], g["excursion"]
    ball = ball0.copy()
    if phase < duty:
        s = phase / duty
        ball.y = ball0.y - e / 2 + e * s
        meta = meta0 + 26 * smooth((s - 0.65) / 0.35)
        toe = 0.0
    else:
        s = (phase - duty) / (1 - duty)
        ball.y = ball0.y + e / 2 - e * smooth(s)
        ball.z = ball0.z + g["lift"] * math.sin(math.pi * s) ** 1.2
        meta = meta0 + 26 * (1 - smooth(s * 1.4)) + 10 * math.sin(math.pi * s)
        toe = 38 * math.sin(math.pi * min(1.0, s * 1.15))
    return ball, meta, toe


def gait_pose(rig, name, t):
    g = GAITS[name]
    phase = (t / g["period"]) % 1.0
    p = Pose()
    rest = rest_feet(rig)
    p.feet = {"L": gait_foot(rest["L"], phase, g), "R": gait_foot(rest["R"], (phase + 0.5) % 1.0, g)}
    w = 2 * math.pi * phase
    run = name == "Run"
    p.root_offset = Vector((0.07 * math.sin(w), 0, -g["crouch"] - g["bob"] * (0.5 + 0.5 * math.cos(2 * w + 0.6))))
    p.add("Hips", rot(X, g["pitch"]) @ rot(Y, 3.0 * math.sin(w)) @ rot(Z, 4.0 * math.sin(w)))
    for i, bone in enumerate(("Spine1", "Spine2", "Chest")):
        p.add(bone, rot(Z, -1.4 * math.sin(w - 0.4 * i)) @ rot(X, 0.6 * math.cos(2 * w)))
    for i, bone in enumerate(("Neck1", "Neck2")):
        p.add(bone, rot(X, -g["pitch"] * 0.6 + 1.5 * math.cos(2 * w + 1.2)) @ rot(Z, -2.0 * math.sin(w - 0.8)))
    p.add("Head", rot(X, -1.0 * math.cos(2 * w + 1.8)) @ rot(Z, -1.5 * math.sin(w - 1.2)))
    p.add("Jaw", rot(X, 2.0 + (3.0 if run else 1.0) * (0.5 + 0.5 * math.sin(2 * w))))
    amp = 3.0 if run else 4.5
    for i in range(1, 7):
        p.add(f"Tail{i}", rot(Z, amp * math.sin(w - 0.55 * i)) @ rot(X, -(0.8 if run else 0.4) * math.cos(2 * w - 0.5 * i)))
    for s, sign in (("L", 1), ("R", -1)):
        p.add(f"UpperArm_{s}", rot(X, 10 * math.sin(2 * w + (0 if run else 1)) - (15 if run else 0)))
        p.add(f"Forearm_{s}", rot(X, -8 * math.sin(2 * w + 0.6)))
    return p


def idle_base(rig, t):
    p = Pose()
    p.feet = rest_feet(rig)
    breathe = math.sin(2 * math.pi * t / 2.4)
    p.root_offset = Vector((0, 0, -0.02 * breathe))
    p.add("Chest", rot(X, 0.8 * breathe))
    for i in range(1, 7):
        p.add(f"Tail{i}", rot(Z, 2.0 * math.sin(2 * math.pi * t / 2.5 - 0.5 * i)))
    return p


def headshake_pose(rig, t, duration=2.5):
    p = idle_base(rig, t)
    env = smooth(t / 0.35) * (1 - smooth((t - duration + 0.5) / 0.5))
    shake = math.sin(2 * math.pi * 2.4 * t)
    p.add("Neck1", rot(Z, 9 * shake * env) @ rot(X, -4 * env))
    p.add("Neck2", rot(Z, 13 * math.sin(2 * math.pi * 2.4 * t - 0.5) * env))
    p.add("Head", rot(Z, 14 * math.sin(2 * math.pi * 2.4 * t - 1.0) * env) @ rot(Y, 8 * shake * env))
    p.add("Jaw", rot(X, 4 + 7 * env * (0.5 + 0.5 * math.sin(2 * math.pi * 4.8 * t))))
    for i in range(1, 7):
        p.add(f"Tail{i}", rot(Z, -4 * shake * env * (i / 6)))
    return p


def roar_pose(rig, t, duration=2.5):
    p = idle_base(rig, t)
    rise = smooth(t / 0.65) * (1 - smooth((t - 1.95) / 0.5))
    jaw = smooth((t - 0.25) / 0.45) * (1 - smooth((t - 1.85) / 0.45))
    tremble = math.sin(2 * math.pi * 11 * t) * jaw
    p.root_offset += Vector((0, 0.10 * rise, 0.05 * rise))
    p.add("Hips", rot(X, -4 * rise))
    p.add("Chest", rot(X, -5 * rise))
    p.add("Neck1", rot(X, -14 * rise + 0.6 * tremble))
    p.add("Neck2", rot(X, -10 * rise) @ rot(Z, 5 * rise))
    p.add("Head", rot(X, -9 * rise + 0.8 * tremble) @ rot(Y, -6 * rise))
    p.add("Jaw", rot(X, 3 + 36 * jaw))
    for s in ("L", "R"):
        p.add(f"UpperArm_{s}", rot(X, -22 * rise))
        p.add(f"Forearm_{s}", rot(X, 18 * rise + 2 * tremble))
        p.add(f"Hand_{s}", rot(X, 15 * rise))
    for i in range(1, 7):
        p.add(f"Tail{i}", rot(X, 3.0 * rise) @ rot(Z, 1.2 * tremble))
    return p


ACTIONS = {
    "Walk": (GAITS["Walk"]["period"], lambda rig, t: gait_pose(rig, "Walk", t)),
    "Run": (GAITS["Run"]["period"], lambda rig, t: gait_pose(rig, "Run", t)),
    "HeadShake": (2.5, headshake_pose),
    "Roar": (2.5, roar_pose),
}


def bake_actions(rig):
    solver = Solver(rig)
    rig.animation_data_create()
    made = []
    for name, (duration, builder) in ACTIONS.items():
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        rig.animation_data.action = action
        frames = round(duration * FPS)
        previous = {}
        for frame in range(frames + 1):
            basis = solver.solve(builder(rig, frame / FPS))
            for bone, m in basis.items():
                pb = rig.pose.bones[bone]
                q = m.to_quaternion()
                if bone in previous:
                    q.make_compatible(previous[bone])
                previous[bone] = q
                pb.rotation_quaternion = q
                pb.location = m.translation
                pb.keyframe_insert("rotation_quaternion", frame=frame, group=bone)
                pb.keyframe_insert("location", frame=frame, group=bone)
        action.frame_range = (0, frames)
        made.append(action)
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    return made


def apply_pose(rig, name, t):
    """Pose the rig directly (for previews)."""
    duration, builder = ACTIONS[name]
    basis = Solver(rig).solve(builder(rig, t))
    for bone, m in basis.items():
        pb = rig.pose.bones[bone]
        pb.rotation_quaternion = m.to_quaternion()
        pb.location = m.translation
