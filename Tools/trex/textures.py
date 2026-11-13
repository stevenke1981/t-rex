"""Materials, shared UV atlas and baked PBR textures for the T-Rex."""
import math
from pathlib import Path

import bpy
import numpy as np

SKIN_PARTS = ("Body", "Tail", "Head", "LowerJaw", "LeftLeg", "RightLeg", "LeftArm", "RightArm")
SLOTS = {
    "Body": ["TRexSkin"], "Tail": ["TRexSkin"],
    "Head": ["TRexSkin", "TRexMouth"], "LowerJaw": ["TRexSkin", "TRexMouth"],
    "LeftLeg": ["TRexSkin", "TRexTeeth"], "RightLeg": ["TRexSkin", "TRexTeeth"],
    "LeftArm": ["TRexSkin", "TRexTeeth"], "RightArm": ["TRexSkin", "TRexTeeth"],
    "UpperTeeth": ["TRexTeeth"], "LowerTeeth": ["TRexTeeth"],
    "LeftEye": ["TRexEye"], "RightEye": ["TRexEye"], "Tongue": ["TRexMouth"],
}
FLAT = {"TRexTeeth": ((0.80, 0.74, 0.58), 0.55), "TRexMouth": ((0.42, 0.13, 0.12), 0.62)}


def _node(tree, kind, **inputs):
    node = tree.nodes.new(kind)
    for key, value in inputs.items():
        node.inputs[key].default_value = value
    return node


def skin_material():
    mat = bpy.data.materials.new("TRexSkin")
    mat.use_nodes = True
    t = mat.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    geo = t.nodes.new("ShaderNodeNewGeometry")
    link = t.links.new
    # Countershading from the surface normal.
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    link(geo.outputs["Normal"], sep.inputs[0])
    shade = _node(t, "ShaderNodeMapRange", **{"From Min": -0.55, "From Max": 0.45})
    link(sep.outputs["Z"], shade.inputs["Value"])
    ramp_node = t.nodes.new("ShaderNodeValToRGB")
    ramp = ramp_node.color_ramp
    ramp.elements[0].color = (0.56, 0.47, 0.32, 1)
    ramp.elements[1].color = (0.12, 0.105, 0.065, 1)
    mid = ramp.elements.new(0.55)
    mid.color = (0.30, 0.24, 0.13, 1)
    link(shade.outputs[0], ramp_node.inputs[0])
    # Dorsal bands, distorted by noise.
    noise = _node(t, "ShaderNodeTexNoise", Scale=1.6, Detail=3.0)
    link(geo.outputs["Position"], noise.inputs["Vector"])
    wave = _node(t, "ShaderNodeTexWave", Scale=0.55, Distortion=5.0, **{"Detail": 2.0})
    wave.bands_direction = "Y"
    link(geo.outputs["Position"], wave.inputs["Vector"])
    band_mask = _node(t, "ShaderNodeMapRange", **{"From Min": 0.15, "From Max": 0.75})
    link(sep.outputs["Z"], band_mask.inputs["Value"])
    band = _node(t, "ShaderNodeMath")
    band.operation = "MULTIPLY"
    band_r = _node(t, "ShaderNodeMapRange", **{"From Min": 0.55, "From Max": 0.8})
    link(wave.outputs["Fac"], band_r.inputs["Value"])
    link(band_r.outputs[0], band.inputs[0])
    link(band_mask.outputs[0], band.inputs[1])
    banded = _node(t, "ShaderNodeMix")
    banded.data_type = "RGBA"
    link(band.outputs[0], banded.inputs["Factor"])
    link(ramp_node.outputs["Color"], banded.inputs["A"])
    banded.inputs["B"].default_value = (0.06, 0.055, 0.04, 1)
    # Scales: voronoi cracks darken, mottling noise varies hue.
    vor = _node(t, "ShaderNodeTexVoronoi", Scale=40.0, Randomness=0.85)
    vor.feature = "DISTANCE_TO_EDGE"
    link(geo.outputs["Position"], vor.inputs["Vector"])
    crack = _node(t, "ShaderNodeMapRange", **{"From Min": 0.0, "From Max": 0.09, "To Min": 0.62, "To Max": 1.0})
    link(vor.outputs["Distance"], crack.inputs["Value"])
    scaled = _node(t, "ShaderNodeMix")
    scaled.data_type = "RGBA"
    scaled.blend_type = "MULTIPLY"
    scaled.inputs["Factor"].default_value = 1.0
    link(banded.outputs["Result"], scaled.inputs["A"])
    link(crack.outputs[0], scaled.inputs["B"])
    mottle = _node(t, "ShaderNodeMix")
    mottle.data_type = "RGBA"
    mottle.blend_type = "OVERLAY"
    mottle.inputs["Factor"].default_value = 0.35
    link(scaled.outputs["Result"], mottle.inputs["A"])
    link(noise.outputs["Color"], mottle.inputs["B"])
    link(mottle.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.72
    # Bump: scales + broad wrinkles.
    wrinkle = _node(t, "ShaderNodeTexNoise", Scale=5.0, Detail=6.0)
    link(geo.outputs["Position"], wrinkle.inputs["Vector"])
    bump_fine = _node(t, "ShaderNodeBump", Strength=0.55, Distance=0.02)
    link(vor.outputs["Distance"], bump_fine.inputs["Height"])
    bump_wide = _node(t, "ShaderNodeBump", Strength=0.25, Distance=0.05)
    link(wrinkle.outputs["Fac"], bump_wide.inputs["Height"])
    link(bump_fine.outputs["Normal"], bump_wide.inputs["Normal"])
    link(bump_wide.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def flat_material(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def eye_material():
    mat = flat_material("TRexEye", (0.8, 0.5, 0.1), 0.1)
    img = eye_image(256)
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def eye_image(size):
    v = np.linspace(0, 1, size)[:, None] * np.ones((1, size))
    u = np.linspace(0, 1, size)[None, :] * np.ones((size, 1))
    rgb = np.zeros((size, size, 3))
    rgb[:] = (0.05, 0.035, 0.02)
    iris = v > 0.70
    shade = np.clip((v - 0.70) / 0.30, 0, 1)
    streak = 0.85 + 0.15 * np.sin(u * 2 * math.pi * 24)
    rgb[iris] = (np.stack([0.95 * streak, 0.55 * streak, 0.08 * streak], -1) * (0.55 + 0.45 * shade[..., None]))[iris]
    slit = (v > 0.86) & (np.abs(np.sin(u * 2 * math.pi)) * (1 - v) < 0.012)
    rgb[slit | (v > 0.975)] = (0.01, 0.01, 0.01)
    return new_image("TRexEye_Albedo", rgb, srgb=True)


def new_image(name, rgb, alpha=None, srgb=True):
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = rgb
    if alpha is not None:
        rgba[..., 3] = alpha
    img.pixels.foreach_set(rgba.ravel())
    return img


def assign_materials(parts):
    mats = {"TRexSkin": skin_material(), "TRexEye": eye_material()}
    for name, (color, rough) in FLAT.items():
        mats[name] = flat_material(name, color, rough)
    for part, obj in parts.items():
        obj.data.materials.clear()
        for slot in SLOTS[part]:
            obj.data.materials.append(mats[slot])
    return mats


# --- UVs & baking ----------------------------------------------------------
def unwrap(objs, margin=0.003):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")


def ensure_uvs(parts):
    unwrap([parts[n] for n in SKIN_PARTS])
    for name in ("UpperTeeth", "LowerTeeth", "Tongue"):
        unwrap([parts[name]], margin=0.01)


def save(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()


def pixels(img):
    w, h = img.size
    arr = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(arr)
    return arr.reshape(h, w, 4)


def bake_skin(parts, size):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 4
    scene.cycles.device = "CPU"
    scene.render.bake.margin = 8
    albedo = bpy.data.images.new("TRexSkin_Albedo", size, size)
    normal = bpy.data.images.new("TRexSkin_Normal", size, size)
    normal.colorspace_settings.name = "Non-Color"
    nodes = []
    for mat in {m for n in SKIN_PARTS for m in parts[n].data.materials}:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        mat.node_tree.nodes.active = node
        nodes.append((mat, node))
    objs = [parts[n] for n in SKIN_PARTS]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    for img, kind in ((albedo, "DIFFUSE"), (normal, "NORMAL")):
        for _, node in nodes:
            node.image = img
        if kind == "DIFFUSE":
            bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True, margin=8)
        else:
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", use_clear=True, margin=8)
    for mat, node in nodes:
        mat.node_tree.nodes.remove(node)
    return albedo, normal


def write_textures(parts, root, size):
    out = Path(root) / "Assets" / "Source" / "Textures"
    ensure_uvs(parts)
    albedo, normal = bake_skin(parts, size)
    save(albedo, out / "TRexSkin" / "Albedo.png")
    save(normal, out / "TRexSkin" / "Normal.png")
    lum = pixels(albedo)[..., :3].mean(-1)
    gloss = np.clip(0.18 + 0.35 * (0.35 - lum), 0.08, 0.4)
    save(new_image("TRexSkin_MG", np.zeros(lum.shape + (3,)), alpha=gloss, srgb=False),
         out / "TRexSkin" / "MetallicGloss.png")
    flat_n = np.ones((16, 16, 3)) * (0.5, 0.5, 1.0)
    for name, (color, rough) in FLAT.items():
        grain = 0.94 + 0.06 * np.random.default_rng(7).random((64, 64, 1))
        save(new_image(f"{name}_A", np.ones((64, 64, 3)) * color * grain), out / name / "Albedo.png")
        save(new_image(f"{name}_N", flat_n, srgb=False), out / name / "Normal.png")
        save(new_image(f"{name}_MG", np.zeros((16, 16, 3)), alpha=np.full((16, 16), 1 - rough), srgb=False),
             out / name / "MetallicGloss.png")
    save(bpy.data.images["TRexEye_Albedo"], out / "TRexEye" / "Albedo.png")
    save(new_image("TRexEye_N", flat_n, srgb=False), out / "TRexEye" / "Normal.png")
    save(new_image("TRexEye_MG", np.zeros((16, 16, 3)), alpha=np.full((16, 16), 0.9), srgb=False),
         out / "TRexEye" / "MetallicGloss.png")
    # Swap the skin to the baked maps so later previews show what Unity gets.
    mat = bpy.data.materials["TRexSkin"]
    t = mat.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    tex = t.nodes.new("ShaderNodeTexImage")
    tex.image = albedo
    t.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])


def bake(parts, root, size):
    write_textures(parts, root, size)
