"""Build the procedural, rigged and split T-Rex for Unity.

Usage (from the repo root):
  blender -b --factory-startup --python-exit-code 1 --python Tools/build_trex.py -- [--preview DIR] [--skip-export]
Writes Assets/Source/Dinosaur/TRex.fbx, Assets/Source/Textures/TRex*/ and Evidence/trex-asset-check.json.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from trex import anim, geometry, rig as rigging, preview, textures  # noqa: E402
from trex.verify import verify_fbx  # noqa: E402

ROOT = TOOLS.parent
FBX = ROOT / "Assets" / "Source" / "Dinosaur" / "TRex.fbx"
EVIDENCE = ROOT / "Evidence" / "trex-asset-check.json"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", help="Directory for preview renders")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--texture-size", type=int, default=2048)
    parser.add_argument("--poses", action="store_true", help="Also render posed previews")
    return parser.parse_args(argv)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = anim.FPS
    scene.unit_settings.system = "METRIC"
    return scene


def export_fbx(rig, parts):
    FBX.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for obj in parts.values():
        obj.select_set(True)
    bpy.context.view_layer.objects.active = rig
    rig.animation_data.action = None
    result = bpy.ops.export_scene.fbx(
        filepath=str(FBX), use_selection=True, axis_forward="-Z", axis_up="Y",
        object_types={"ARMATURE", "MESH"}, use_mesh_modifiers=False, mesh_smooth_type="OFF",
        use_tspace=True, use_metadata=False, add_leaf_bones=False, primary_bone_axis="Y",
        secondary_bone_axis="X", bake_anim=True, bake_anim_use_all_bones=True,
        bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
        bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0,
        path_mode="STRIP", embed_textures=False)
    if result != {"FINISHED"} or not FBX.is_file():
        raise RuntimeError("FBX export failed")


def main():
    args = parse_args()
    reset_scene()
    parts = geometry.build_all()
    rig = rigging.build_armature()
    rigging.skin_all(parts, rig)
    textures.assign_materials(parts)
    if args.preview:
        preview.render_views(args.preview, prefix="rest_")
    actions = [a.name for a in anim.bake_actions(rig)]
    if args.preview and args.poses:
        scene = bpy.context.scene
        for name, t in (("Walk", 0.5), ("Run", 0.25), ("HeadShake", 1.0), ("Roar", 1.2)):
            anim.apply_pose(rig, name, t)
            bpy.context.view_layer.update()
            preview.render_views(args.preview, views=["side", "front34"], prefix=f"{name}_")
        for pb in rig.pose.bones:
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.location = (0, 0, 0)
    if args.skip_export:
        return
    textures.bake(parts, ROOT, args.texture_size)
    if args.preview:
        preview.render_views(args.preview, views=["front34", "head"], prefix="textured_")
    export_fbx(rig, parts)
    report = verify_fbx(FBX, expected_parts=list(parts), expected_actions=list(anim.ACTIONS))
    report["gaitSpeedsBlenderMetresPerSecond"] = {g: round(anim.gait_speed(g), 4) for g in anim.GAITS}
    report["gaits"] = anim.GAITS
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[build_trex] OK {FBX} parts={len(parts)} actions={actions}")


if __name__ == "__main__":
    main()
