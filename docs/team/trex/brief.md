# T-Rex Unity 專案共用 brief

目標：仿 `unity-stegosaur-forest`（唯讀參考：scratchpad/ref）之流程，以 Blender 程序化建出分件蒙皮暴龍 FBX，Unity Editor 腳本組森林場景並批次渲染五鏡頭。

## 共用契約（主控定案，勿改）
- FBX：`Assets/Source/Dinosaur/TRex.fbx`；manifest model id `trex`；Prefab／場景根物件名 `TRex`。
- 場景：`Assets/Scenes/TRexForest.unity`。
- 骨架物件 `TRexArmature`；骨骼名（底線，不用點）：
  `Root, Hips, Spine1, Spine2, Chest, Neck1, Neck2, Head, Jaw, Tail1..Tail6,
   Thigh_L/R, Shin_L/R, Foot_L/R, Toe_L/R, UpperArm_L/R, Forearm_L/R, Hand_L/R`。
- 動作（FBX 內 clip 名，Unity 可能帶 `TRexArmature|` 前綴）：`Walk`(2.0s 循環)、`Run`(1.0s 循環)、`HeadShake`(2.5s)、`Roar`(2.5s，Jaw 張口)。24 fps。
- 分件蒙皮網格（各自獨立 SkinnedMeshRenderer，共用一副骨架）：
  `Body, Head, LowerJaw, Tail, LeftLeg, RightLeg, LeftArm, RightArm, UpperTeeth, LowerTeeth, LeftEye, RightEye, Tongue`。
  朝向判定：`Head` 與 `Tail` 兩件包圍盒中心之差。
- 材質槽：`TRexSkin, TRexTeeth, TRexEye, TRexMouth`，貼圖 `Assets/Source/Textures/<slot>/{Albedo,Normal,MetallicGloss}.png`。
- 五鏡頭：`Walk, Run, HeadShake, Roar, Orbit`；量測骨骼：Walk/Run/Orbit→`Thigh_L`，HeadShake→`Head`，Roar→`Jaw`。
- C# namespace `TRexForest`；選單 `TRex/Build Forest Scene`、`TRex/Render Forest Film`、`TRex/Render Forest Smoke Test`；batch 方法 `TRexForest.ForestRender.RenderBatch`。

## 硬規則
- 只動自己名下檔案；不得 git add／commit／stash／checkout；不新增依賴。
- Unity 授權／渲染由主控執行；agent 只做靜態修改與語法自檢。

## 回報格式
改動檔案、每檔要點、未驗證項、疑慮。
