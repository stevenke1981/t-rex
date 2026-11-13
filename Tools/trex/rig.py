"""T-Rex armature and distance-based skin weights."""
import bpy
from mathutils import Vector

from .geometry import head_point

# name: (head, tail, parent)
BONES = {
    "Root": ((0, 0, 0), (0, -1.0, 0), None),
    "Hips": ((0, 0.60, 3.85), (0, -0.50, 3.75), "Root"),
    "Spine1": ((0, -0.50, 3.75), (0, -1.50, 3.55), "Hips"),
    "Spine2": ((0, -1.50, 3.55), (0, -2.50, 3.45), "Spine1"),
    "Chest": ((0, -2.50, 3.45), (0, -3.30, 3.60), "Spine2"),
    "Neck1": ((0, -3.30, 3.60), (0, -3.95, 4.10), "Chest"),
    "Neck2": ((0, -3.95, 4.10), (0, -4.50, 4.50), "Neck1"),
    "Head": ((0, -4.50, 4.50), head_point((0, -6.00, 4.60)), "Neck2"),
    "Jaw": (head_point((0, -4.55, 4.15)), head_point((0, -5.95, 4.18)), "Head"),
    "Tail1": ((0, 0.60, 3.85), (0, 1.60, 3.80), "Hips"),
    "Tail2": ((0, 1.60, 3.80), (0, 2.60, 3.75), "Tail1"),
    "Tail3": ((0, 2.60, 3.75), (0, 3.60, 3.66), "Tail2"),
    "Tail4": ((0, 3.60, 3.66), (0, 4.60, 3.52), "Tail3"),
    "Tail5": ((0, 4.60, 3.52), (0, 5.60, 3.36), "Tail4"),
    "Tail6": ((0, 5.60, 3.36), (0, 6.80, 3.12), "Tail5"),
}
for s, sx in (("L", 1), ("R", -1)):
    BONES.update({
        f"Thigh_{s}": ((0.74 * sx, 0.05, 3.45), (0.86 * sx, -0.62, 2.05), "Hips"),
        f"Shin_{s}": ((0.86 * sx, -0.62, 2.05), (0.86 * sx, 0.25, 0.80), f"Thigh_{s}"),
        f"Foot_{s}": ((0.86 * sx, 0.25, 0.80), (0.86 * sx, -0.08, 0.20), f"Shin_{s}"),
        f"Toe_{s}": ((0.86 * sx, -0.08, 0.20), (0.86 * sx, -0.92, 0.07), f"Foot_{s}"),
        f"UpperArm_{s}": ((0.58 * sx, -2.86, 2.98), (0.66 * sx, -3.10, 2.55), "Chest"),
        f"Forearm_{s}": ((0.66 * sx, -3.10, 2.55), (0.63 * sx, -3.62, 2.42), f"UpperArm_{s}"),
        f"Hand_{s}": ((0.63 * sx, -3.62, 2.42), (0.64 * sx, -3.82, 2.30), f"Forearm_{s}"),
    })

# Which bones may influence each part (rigid parts list one bone).
PART_BONES = {
    "Body": ["Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head"],
    "Tail": ["Hips", "Tail1", "Tail2", "Tail3", "Tail4", "Tail5", "Tail6"],
    "Head": ["Head"],
    "UpperTeeth": ["Head"],
    "LeftEye": ["Head"],
    "RightEye": ["Head"],
    "LowerJaw": ["Jaw"],
    "LowerTeeth": ["Jaw"],
    "Tongue": ["Jaw"],
}
for s, side in (("L", "Left"), ("R", "Right")):
    PART_BONES[f"{side}Leg"] = ["Hips", f"Thigh_{s}", f"Shin_{s}", f"Foot_{s}", f"Toe_{s}"]
    PART_BONES[f"{side}Arm"] = ["Chest", f"UpperArm_{s}", f"Forearm_{s}", f"Hand_{s}"]


def build_armature():
    data = bpy.data.armatures.new("TRexArmature")
    rig = bpy.data.objects.new("TRexArmature", data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = data.edit_bones
    for name, (head, tail, parent) in BONES.items():
        bone = edit.new(name)
        bone.head, bone.tail = head, tail
        bone.roll = 0.0
        if parent:
            bone.parent = edit[parent]
            bone.use_connect = Vector(edit[parent].tail) == Vector(head) and name != "Jaw"
        bone.use_deform = name != "Root"
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return rig


def segment_distance(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length, t


def skin(obj, rig, bones, power=5.0, keep=3):
    """Weight obj to the listed bones by inverse distance to bone segments."""
    groups = {name: obj.vertex_groups.new(name=name) for name in bones}
    segs = {name: (Vector(BONES[name][0]), Vector(BONES[name][1])) for name in bones}
    for v in obj.data.vertices:
        p = v.co
        if len(bones) == 1:
            groups[bones[0]].add([v.index], 1.0, "REPLACE")
            continue
        scores = []
        for name in bones:
            d, _ = segment_distance(p, *segs[name])
            # Hips only owns the very top of the thigh / tail root.
            if name == "Hips" and (obj.name.endswith("Leg") or obj.name == "Tail"):
                d *= 1.9
            if name == "Chest" and obj.name.endswith("Arm"):
                d *= 1.6
            scores.append((1.0 / (d + 0.02) ** power, name))
        scores.sort(reverse=True)
        top = scores[:keep]
        total = sum(s for s, _ in top)
        for s, name in top:
            groups[name].add([v.index], s / total, "REPLACE")
    obj.parent = rig
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mod.use_vertex_groups = True


def skin_all(parts, rig):
    for name, obj in parts.items():
        skin(obj, rig, PART_BONES[name])
