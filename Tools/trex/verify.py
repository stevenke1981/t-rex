"""Re-import the exported FBX in a clean scene and check parts, rig and actions."""
import hashlib

import bpy


def verify_fbx(path, expected_parts, expected_actions):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False)
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(rigs) != 1:
        raise RuntimeError(f"Expected one armature, found {len(rigs)}")
    rig = rigs[0]
    names = sorted(o.name for o in meshes)
    missing = sorted(set(expected_parts) - set(names))
    if missing:
        raise RuntimeError(f"Missing parts after re-import: {missing}")
    for obj in meshes:
        if not any(m.type == "ARMATURE" for m in obj.modifiers) and obj.parent != rig:
            raise RuntimeError(f"{obj.name} is not bound to the rig")
        if not obj.vertex_groups:
            raise RuntimeError(f"{obj.name} has no skin weights")
    actions = {}
    probe = {"Walk": "Thigh_L", "Run": "Thigh_L", "HeadShake": "Head", "Roar": "Jaw"}
    rig.animation_data_create()
    for action in bpy.data.actions:
        short = action.name.split("|")[-1]
        if short not in expected_actions:
            continue
        rig.animation_data.action = action
        if action.slots:
            rig.animation_data.action_slot = action.slots[0]
        first, last = action.frame_range
        scene = bpy.context.scene
        bone = rig.pose.bones[probe[short]]
        quats = []
        for frame in (first, (first + last) / 2, first + (last - first) * 0.25):
            scene.frame_set(int(frame))
            quats.append(bone.matrix.to_quaternion())
        angle = max(min(a, 6.283185307 - a) for a in (quats[0].rotation_difference(q).angle for q in quats[1:]))
        if angle < 0.01:
            raise RuntimeError(f"Action {action.name} does not move {bone.name}")
        actions[short] = {"importedName": action.name, "frames": [first, last],
                          "seconds": round((last - first) / scene.render.fps, 4),
                          "probeBone": bone.name, "probeDegrees": round(angle * 57.29578, 3)}
    if sorted(actions) != sorted(expected_actions):
        raise RuntimeError(f"Actions after re-import: {sorted(actions)}")
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    return {
        "fbx": str(path.name),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "blenderVersion": bpy.app.version_string,
        "parts": names,
        "partCount": len(names),
        "boneCount": len(rig.data.bones),
        "triangles": tris,
        "actions": actions,
    }
