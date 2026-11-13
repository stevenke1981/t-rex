"""Quick Blender renders for visual checks of the generated T-Rex."""
import math
from pathlib import Path

import bpy
from mathutils import Vector


def set_engine(scene):
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES"):
        try:
            scene.render.engine = engine
            return engine
        except TypeError:
            continue
    raise RuntimeError("No usable render engine")


def setup(scene, resolution=(960, 540)):
    set_engine(scene)
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.55, 0.62, 0.7, 1)
    bg.inputs[1].default_value = 0.8
    scene.world = world
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    scene.collection.objects.link(sun)
    if "PreviewGround" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
        bpy.context.active_object.name = "PreviewGround"
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    cam.data.lens = 35
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def shoot(scene, cam, path, location, target, lens=35):
    cam.data.lens = lens
    cam.location = Vector(location)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


VIEWS = {
    "side": ((17, 0.5, 3.0), (0, 0.4, 2.6), 35),
    "front34": ((-9, -14, 5.5), (0, -2.5, 3.0), 35),
    "back34": ((10, 11, 6.5), (0, 0, 2.8), 35),
    "head": ((-3.2, -8.2, 5.4), (0, -5.1, 4.6), 50),
    "top": ((0.01, 0, 22), (0, 0, 0), 35),
}


def render_views(out_dir, views=None, prefix=""):
    scene = bpy.context.scene
    cam = setup(scene) if scene.camera is None else scene.camera
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in views or VIEWS:
        loc, target, lens = VIEWS[name]
        shoot(scene, cam, out_dir / f"{prefix}{name}.png", loc, target, lens)
