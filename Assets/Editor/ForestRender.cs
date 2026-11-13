using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace TRexForest
{
    public static class ForestRender
    {
        private const string DinosaurFbx = "Assets/Source/Dinosaur/TRex.fbx";
        private const string ReportFile = "render-report.json";
        private const float ShotSeconds = 2.5f;
        // Camera framing and travel distances were authored for a 6.5 m reference character and scale with the T-Rex length.
        // Retune here (or ForestSceneBuilder.CharacterLength) to change every character-relative distance at once.
        private const float ReferenceCharacterLength = 6.5f;
        private const float CharacterScale = ForestSceneBuilder.CharacterLength / ReferenceCharacterLength;
        // Ground speeds of the in-place Walk/Run cycles in Unity metres per second: Blender gait speed
        // (Evidence/trex-asset-check.json) x imported scale (9 m / 13.72 m). Anchor travel matches them so feet do not slide.
        private const float WalkGroundSpeed = 1.06f;
        private const float RunGroundSpeed = 3.90f;
        private const float RunStart = -4.7f * CharacterScale;
        private const float WalkStart = RunStart - WalkGroundSpeed * ShotSeconds;
        private const float StopPosition = RunStart + RunGroundSpeed * ShotSeconds;
        private const float OrbitRadius = 1.65f * CharacterScale;

        private static readonly string[] ShotNames = { "Walk", "Run", "HeadShake", "Roar", "Orbit" };

        [MenuItem("TRex/Render Forest Film")]
        public static void RenderFromMenu()
        {
            Capture(NewOutputDirectory(), 1280, 720, 24, false);
        }

        [MenuItem("TRex/Render Forest Smoke Test")]
        public static void SmokeFromMenu()
        {
            Capture(NewOutputDirectory(), 1280, 720, 24, true);
        }

        public static void RenderBatch()
        {
            string[] args = Environment.GetCommandLineArgs();
            string output = GetArgument(args, "-forest-output", null) ?? NewOutputDirectory();
            int width = int.Parse(GetArgument(args, "-forest-width", "1280"), CultureInfo.InvariantCulture);
            int height = int.Parse(GetArgument(args, "-forest-height", "720"), CultureInfo.InvariantCulture);
            int fps = int.Parse(GetArgument(args, "-forest-fps", "24"), CultureInfo.InvariantCulture);
            Capture(output, width, height, fps, args.Contains("-forest-smoke"));
        }

        private static void Capture(string output, int width, int height, int fps, bool smoke)
        {
            if (width < 64 || width > 3840 || height < 64 || height > 2160 ||
                width % 2 != 0 || height % 2 != 0 || fps < 2 || fps > 60)
                throw new ArgumentOutOfRangeException(nameof(width), "Use even dimensions from 64×64 to 3840×2160 and 2–60 fps.");
            if (EditorApplication.isPlayingOrWillChangePlaymode)
                throw new InvalidOperationException("Exit Play mode before capturing the forest.");
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                throw new InvalidOperationException("Capture requires Unity to start with a graphics device.");

            string outputPath = Path.GetFullPath(output);
            string framesPath = Path.Combine(outputPath, "frames");
            string reportPath = Path.Combine(outputPath, ReportFile);
            if (Directory.Exists(framesPath) || File.Exists(reportPath))
                throw new IOException($"A capture already exists at {outputPath}. Choose a new output directory.");

            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != ForestSceneBuilder.ScenePath)
            {
                if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                    return;
                if (AssetDatabase.LoadAssetAtPath<SceneAsset>(ForestSceneBuilder.ScenePath) != null)
                    EditorSceneManager.OpenScene(ForestSceneBuilder.ScenePath, OpenSceneMode.Single);
                else
                    ForestSceneBuilder.Build();
                scene = SceneManager.GetActiveScene();
            }

            GameObject anchor = scene.GetRootGameObjects().SingleOrDefault(root => root.name == "TRex");
            Camera sceneCamera = Camera.main;
            if (anchor == null || anchor.transform.childCount != 1 ||
                sceneCamera == null || sceneCamera.gameObject.scene != scene)
                throw new InvalidOperationException("The forest needs the TRex anchor, its rig child, and a MainCamera in the active scene.");

            Transform subject = anchor.transform;
            GameObject model = subject.GetChild(0).gameObject;
            SkinnedMeshRenderer[] pieces = model.GetComponentsInChildren<SkinnedMeshRenderer>();
            if (pieces.Length == 0)
                throw new InvalidOperationException("The assembled T-Rex has no visible skinned mesh parts.");
            Transform[] skeleton = model.GetComponentsInChildren<Transform>(true);
            Transform face = FindBone(skeleton, "Head"); // camera focus for close-ups: back of the skull
            Transform head = FindBone(skeleton, "Head");
            Transform jaw = FindBone(skeleton, "Jaw");
            Transform leg = FindBone(skeleton, "Thigh_L");

            Bounds bounds = pieces[0].bounds;
            foreach (SkinnedMeshRenderer piece in pieces.Skip(1))
                bounds.Encapsulate(piece.bounds);
            Vector3 center = subject.InverseTransformPoint(bounds.center);
            TransformPose anchorPose = new TransformPose(subject);
            TransformPose[] rigPose = skeleton.Select(node => new TransformPose(node)).ToArray();
            TransformPose modelPose = new TransformPose(model.transform);
            bool[] updateWhenOffscreen = pieces.Select(piece => piece.updateWhenOffscreen).ToArray();
            bool[] recalculatePerRender = pieces.Select(piece => piece.forceMatrixRecalculationPerRender).ToArray();

            AnimationClip[] imported = AssetDatabase.LoadAllAssetRepresentationsAtPath(DinosaurFbx).OfType<AnimationClip>().ToArray();
            AnimationClip[] clips = ShotNames.Take(4).Select(name => FindClip(imported, name)).ToArray();
            int shotFrames = Mathf.RoundToInt(ShotSeconds * fps);
            int totalFrames = smoke ? ShotNames.Length * 3 : ShotNames.Length * shotFrames;
            var report = new CaptureReport
            {
                unityVersion = Application.unityVersion,
                graphicsDevice = SystemInfo.graphicsDeviceName,
                graphicsApi = SystemInfo.graphicsDeviceType.ToString(),
                colorSpace = QualitySettings.activeColorSpace.ToString(),
                width = width,
                height = height,
                frameRate = fps,
                smoke = smoke,
                skinnedParts = pieces.Select(piece => piece.name).OrderBy(name => name, StringComparer.Ordinal).ToArray(),
                shots = new ShotReport[ShotNames.Length]
            };

            GameObject cameraObject = null;
            RenderTexture target = null;
            Texture2D pixels = null;
            RenderTexture previousTarget = RenderTexture.active;
            int outputFrame = 0;
            try
            {
                foreach (SkinnedMeshRenderer piece in pieces)
                {
                    piece.updateWhenOffscreen = true;
                    // Unity 6.4 batch capture does not re-skin after SampleAnimation unless forced per render.
                    piece.forceMatrixRecalculationPerRender = true;
                }

                cameraObject = new GameObject("Forest Capture Camera") { hideFlags = HideFlags.HideAndDontSave };
                Camera camera = cameraObject.AddComponent<Camera>();
                camera.CopyFrom(sceneCamera);
                camera.enabled = false;
                camera.usePhysicalProperties = false;
                camera.allowHDR = false;
                camera.nearClipPlane = 0.08f;
                camera.aspect = width / (float)height;

                target = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
                camera.targetTexture = target;
                pixels = new Texture2D(width, height, TextureFormat.RGB24, false, false);
                Directory.CreateDirectory(framesPath);

                for (int shot = 0; shot < ShotNames.Length; shot++)
                {
                    foreach (TransformPose rest in rigPose)
                        rest.Restore();

                    AnimationClip clip = clips[shot == 4 ? 0 : shot];
                    Transform drivenBone = shot switch { 2 => head, 3 => jaw, _ => leg };
                    float rotation = VerifyBoneMotion(model, clip, drivenBone);
                    var detail = new ShotReport
                    {
                        name = ShotNames[shot],
                        clip = clip.name,
                        clipSeconds = clip.length,
                        measuredBone = drivenBone.name,
                        boneRotationDegrees = rotation,
                        firstFrame = outputFrame,
                        sourceFrames = shotFrames
                    };
                    IEnumerable<int> sampleFrames = smoke
                        ? new[] { 0, shotFrames / 2, shotFrames - 1 }
                        : Enumerable.Range(0, shotFrames);

                    foreach (int frame in sampleFrames)
                    {
                        if (!Application.isBatchMode && EditorUtility.DisplayCancelableProgressBar(
                                "Rendering T-Rex Forest", $"{detail.name}  {outputFrame + 1}/{totalFrames}",
                                outputFrame / (float)totalFrames))
                            throw new OperationCanceledException("Forest capture was canceled. Partial frames were kept.");

                        float progress = frame / (float)(shotFrames - 1);
                        float seconds = frame / (float)fps;
                        float poseTime = (shot == 2 || shot == 3)
                            ? clip.length * progress
                            : Mathf.Repeat(seconds, clip.length);
                        clip.SampleAnimation(model, poseTime);
                        modelPose.Restore();
                        ComposeShot(shot, progress, subject, anchorPose.LocalPosition, center, face, camera);

                        if (frame == 0)
                        {
                            detail.anchorStart = subject.position;
                            detail.cameraStart = camera.transform.position;
                        }
                        if (frame == shotFrames - 1)
                        {
                            detail.anchorEnd = subject.position;
                            detail.cameraEnd = camera.transform.position;
                        }

                        camera.Render();
                        RenderTexture.active = target;
                        pixels.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
                        File.WriteAllBytes(Path.Combine(framesPath, $"frame_{outputFrame:D5}.png"), pixels.EncodeToPNG());
                        outputFrame++;
                    }

                    detail.frameCount = outputFrame - detail.firstFrame;
                    report.shots[shot] = detail;
                    Debug.Log($"[TRexForest] {detail.name}: {detail.frameCount} frames, {detail.measuredBone} moved {rotation:F2}°.");
                }

                report.frameCount = outputFrame;
                File.WriteAllText(reportPath, JsonUtility.ToJson(report, true) + Environment.NewLine);
                Debug.Log($"[TRexForest] Captured {outputFrame} frames to {outputPath}");
            }
            finally
            {
                RenderTexture.active = previousTarget;
                if (cameraObject != null)
                    Object.DestroyImmediate(cameraObject);
                if (target != null)
                    RenderTexture.ReleaseTemporary(target);
                if (pixels != null)
                    Object.DestroyImmediate(pixels);
                foreach (TransformPose rest in rigPose)
                    rest.Restore();
                anchorPose.Restore();
                for (int i = 0; i < pieces.Length; i++)
                {
                    pieces[i].updateWhenOffscreen = updateWhenOffscreen[i];
                    pieces[i].forceMatrixRecalculationPerRender = recalculatePerRender[i];
                }
                if (!Application.isBatchMode)
                    EditorUtility.ClearProgressBar();
            }
        }

        private static void ComposeShot(int shot, float progress, Transform subject, Vector3 origin,
            Vector3 center, Transform face, Camera camera)
        {
            float curve = Mathf.SmoothStep(0f, 1f, progress);
            float yaw = 0f;
            Vector3 offset;
            switch (shot)
            {
                case 0:
                    offset = new Vector3(0f, 0f, Mathf.Lerp(WalkStart, RunStart, progress));
                    break;
                case 1:
                    offset = new Vector3(0f, 0f, Mathf.Lerp(RunStart, StopPosition, progress));
                    break;
                case 4:
                    float arc = 1.16f * progress;
                    yaw = -arc * Mathf.Rad2Deg;
                    offset = new Vector3(-OrbitRadius * (1f - Mathf.Cos(arc)), 0f, StopPosition + OrbitRadius * Mathf.Sin(arc));
                    break;
                default:
                    offset = new Vector3(0f, 0f, StopPosition);
                    break;
            }

            subject.localPosition = origin + offset;
            subject.localRotation = Quaternion.Euler(0f, yaw, 0f);
            Vector3 position;
            Vector3 focus = subject.TransformPoint(center);
            float fieldOfView;
            switch (shot)
            {
                case 0:
                    position = subject.position + Scaled(new Vector3(Mathf.Lerp(-4.0f, -3.65f, curve),
                        Mathf.Lerp(1.75f, 1.95f, curve), Mathf.Lerp(1.7f, 2.35f, curve)));
                    focus += Scaled(subject.forward * 0.45f + Vector3.up * 0.22f);
                    fieldOfView = 60f;
                    break;
                case 1:
                    // Lateral distance stays unscaled so the camera keeps clear of the roadside shrubs (x >= 5.3).
                    position = subject.position + new Vector3(4.6f, Mathf.Lerp(0.86f, 1.13f, curve) * CharacterScale,
                        Mathf.Lerp(-0.85f, 1.05f, curve) * CharacterScale);
                    focus += Scaled(Vector3.down * 0.18f + subject.forward * Mathf.Lerp(-0.20f, 0.50f, curve));
                    fieldOfView = 59f;
                    break;
                case 2:
                    position = subject.position + Scaled(new Vector3(Mathf.Lerp(-3.0f, -2.55f, curve),
                        Mathf.Lerp(1.86f, 1.74f, curve), 4.88f));
                    focus = face.position + Scaled(Vector3.up * 0.13f);
                    fieldOfView = 32f;
                    break;
                case 3:
                    position = subject.position + Scaled(new Vector3(Mathf.Lerp(3.1f, 2.72f, curve),
                        Mathf.Lerp(1.1f, 1.43f, curve), Mathf.Lerp(5.2f, 4.95f, curve)));
                    focus = face.position + Scaled(Vector3.up * 0.15f);
                    fieldOfView = 36f;
                    break;
                default:
                    float angle = Mathf.Lerp(57f, 168f, curve) * Mathf.Deg2Rad;
                    position = new Vector3(origin.x + 4.12f * CharacterScale * Mathf.Sin(angle),
                        subject.position.y + Mathf.Lerp(2.38f, 2.65f, curve) * CharacterScale,
                        subject.position.z + 5.7f * CharacterScale * Mathf.Cos(angle));
                    focus += Scaled(Vector3.down * 0.25f);
                    fieldOfView = 61f;
                    break;
            }

            camera.fieldOfView = fieldOfView;
            camera.transform.SetPositionAndRotation(position, Quaternion.LookRotation(focus - position, Vector3.up));
        }

        private static Vector3 Scaled(Vector3 offset) => offset * CharacterScale;

        private static Transform FindBone(Transform[] nodes, string name)
        {
            // The skinned mesh parts reuse part names such as "Head", so bones are the transforms without a renderer.
            return nodes.Single(node => node.name == name && !node.GetComponent<Renderer>());
        }

        private static float VerifyBoneMotion(GameObject model, AnimationClip clip, Transform bone)
        {
            clip.SampleAnimation(model, 0f);
            Quaternion start = bone.localRotation;
            float rotation = 0f;
            for (int i = 1; i < 8; i++)
            {
                clip.SampleAnimation(model, clip.length * i / 8f);
                rotation = Mathf.Max(rotation, Quaternion.Angle(start, bone.localRotation));
            }

            if (rotation < 0.1f)
                throw new InvalidOperationException($"Clip {clip.name} did not animate {bone.name} on {model.name}.");
            return rotation;
        }

        private static AnimationClip FindClip(AnimationClip[] clips, string name)
        {
            AnimationClip[] matches = clips.Where(clip => clip.name == name ||
                clip.name.EndsWith("|" + name, StringComparison.Ordinal) ||
                clip.name.EndsWith(":" + name, StringComparison.Ordinal)).ToArray();
            if (matches.Length != 1 || matches[0].length <= 0f)
                throw new InvalidOperationException($"Expected one non-empty {name} clip in {DinosaurFbx}. Found: {string.Join(", ", clips.Select(clip => clip.name))}.");
            return matches[0];
        }

        private static string GetArgument(string[] args, string name, string fallback)
        {
            int index = Array.IndexOf(args, name);
            if (index < 0)
                return fallback;
            if (index + 1 == args.Length || args[index + 1].StartsWith("-", StringComparison.Ordinal))
                throw new ArgumentException($"{name} requires a value.");
            return args[index + 1];
        }

        private static string NewOutputDirectory()
        {
            string project = Directory.GetParent(Application.dataPath).FullName;
            return Path.Combine(project, "Render", $"unity-{DateTime.Now:yyyyMMdd-HHmmss}-{Guid.NewGuid().ToString("N").Substring(0, 8)}");
        }

        private readonly struct TransformPose
        {
            private readonly Transform node;
            private readonly Quaternion rotation;
            private readonly Vector3 scale;
            public Vector3 LocalPosition { get; }

            public TransformPose(Transform node)
            {
                this.node = node;
                LocalPosition = node.localPosition;
                rotation = node.localRotation;
                scale = node.localScale;
            }

            public void Restore()
            {
                node.localPosition = LocalPosition;
                node.localRotation = rotation;
                node.localScale = scale;
            }
        }

        [Serializable]
        private sealed class CaptureReport
        {
            public string unityVersion;
            public string graphicsDevice;
            public string graphicsApi;
            public string colorSpace;
            public int width;
            public int height;
            public int frameRate;
            public int frameCount;
            public bool smoke;
            public string[] skinnedParts;
            public ShotReport[] shots;
        }

        [Serializable]
        private sealed class ShotReport
        {
            public string name;
            public string clip;
            public string measuredBone;
            public float clipSeconds;
            public float boneRotationDegrees;
            public int firstFrame;
            public int frameCount;
            public int sourceFrames;
            public Vector3 anchorStart;
            public Vector3 anchorEnd;
            public Vector3 cameraStart;
            public Vector3 cameraEnd;
        }
    }
}
