"""Motion regressions. Run with Blender --background --python-exit-code 1 --python Tools/test_trex_motion.py."""
import math
import sys
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trex import anim, geometry, rig as rigging  # noqa: E402


class GaitMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cls.rig = rigging.build_armature()
        cls.legs = {name: geometry.build_leg(side) for name, side in
                    (("LeftLeg", "L"), ("RightLeg", "R"))}
        rigging.skin_all(cls.legs, cls.rig)
        cls.ground = min(v.co.z for obj in cls.legs.values() for v in obj.data.vertices)

    def test_gait_mesh_clears_the_rest_ground(self):
        for name, gait in anim.GAITS.items():
            with self.subTest(gait=name):
                lowest, at = math.inf, 0.0
                for frame in range(round(gait["period"] * anim.FPS * 4) + 1):
                    t = frame / (anim.FPS * 4)
                    anim.apply_pose(self.rig, name, t)
                    bpy.context.view_layer.update()
                    graph = bpy.context.evaluated_depsgraph_get()
                    for obj in self.legs.values():
                        evaluated = obj.evaluated_get(graph)
                        mesh = evaluated.to_mesh()
                        height = min((evaluated.matrix_world @ v.co).z for v in mesh.vertices)
                        evaluated.to_mesh_clear()
                        if height < lowest:
                            lowest, at = height, t
                self.assertGreaterEqual(
                    lowest, self.ground - 0.001,
                    f"{name} at {at:.4f}s: mesh is {self.ground - lowest:.4f}m below rest ground")

    def test_arms_swing_in_opposite_phases(self):
        for name, gait in anim.GAITS.items():
            poses = [anim.gait_pose(self.rig, name, frame / anim.FPS)
                     for frame in range(round(gait["period"] * anim.FPS))]
            for joint in ("UpperArm", "Forearm"):
                with self.subTest(gait=name, joint=joint):
                    left = [p.rot[f"{joint}_L"].to_euler().x for p in poses]
                    right = [p.rot[f"{joint}_R"].to_euler().x for p in poses]
                    self.assertGreater(max(left) - min(left), math.radians(10))
                    self.assertGreater(max(right) - min(right), math.radians(10))
                    left = [a - sum(left) / len(left) for a in left]
                    right = [a - sum(right) / len(right) for a in right]
                    correlation = sum(a * b for a, b in zip(left, right)) / math.sqrt(
                        sum(a * a for a in left) * sum(b * b for b in right))
                    self.assertLess(correlation, -0.9, f"{name} {joint} correlation={correlation:.3f}")

    def test_gait_cycles_join_without_a_pose_jump(self):
        solver = anim.Solver(self.rig)
        for name, gait in anim.GAITS.items():
            start = solver.solve(anim.gait_pose(self.rig, name, 0))
            # Exactly one period wraps to phase zero and would conceal a jump at the seam.
            end = solver.solve(anim.gait_pose(self.rig, name, gait["period"] * (1 - 1e-6)))
            for bone in start:
                with self.subTest(gait=name, bone=bone):
                    self.assertLess((start[bone].translation - end[bone].translation).length, 1e-4)
                    self.assertLess(start[bone].to_quaternion().rotation_difference(
                        end[bone].to_quaternion()).angle, 0.001)

    def test_planted_toes_do_not_slide_with_matching_root_speed(self):
        for name, gait in anim.GAITS.items():
            for side, offset in (("L", 0.0), ("R", 0.5)):
                planted = []
                for step in range(11):
                    t = gait["period"] * (offset + gait["duty"] * 0.99 * step / 10)
                    anim.apply_pose(self.rig, name, t)
                    bpy.context.view_layer.update()
                    point = self.rig.pose.bones[f"Toe_{side}"].tail.copy()
                    point.y -= anim.gait_speed(name) * t
                    planted.append(point)
                with self.subTest(gait=name, side=side):
                    self.assertLess(max((p - planted[0]).length for p in planted), 0.001)

    def test_baked_gaits_keep_planted_toes_in_place(self):
        actions = {a.name: a for a in anim.bake_actions(self.rig)}
        scene = bpy.context.scene
        for name, gait in anim.GAITS.items():
            self.rig.animation_data.action = actions[name]
            self.rig.animation_data.action_slot = actions[name].slots[0]
            for side, offset in (("L", 0.0), ("R", 0.5)):
                planted = []
                for step in range(11):
                    t = gait["period"] * (offset + gait["duty"] * 0.99 * step / 10)
                    frame = (t % gait["period"]) * anim.FPS
                    scene.frame_set(math.floor(frame), subframe=frame % 1)
                    point = self.rig.pose.bones[f"Toe_{side}"].tail.copy()
                    point.y -= anim.gait_speed(name) * t
                    planted.append(point)
                with self.subTest(gait=name, side=side):
                    self.assertLess(max((p - planted[0]).length for p in planted), 0.001)
        self.rig.animation_data.action = None


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0]], exit=False)
    if not result.result.wasSuccessful():
        raise RuntimeError("T-Rex motion regressions failed")
