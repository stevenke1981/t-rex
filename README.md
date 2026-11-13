# Unity 暴龍森林

仿 [unity-stegosaur-forest](https://github.com/stevenke1981/unity-stegosaur-forest) 的流程：Blender 腳本產出分件蒙皮 FBX 與動作，Unity Editor 腳本組裝森林場景，再批次渲染五鏡頭影片。暴龍沒有外部來源模型，由 `Tools/build_trex.py` 在 Blender 中程序化建模、綁骨、做動作、烘焙貼圖。

- [Unity 操作與驗證紀錄](docs/操作紀錄.md)
- [素材來源與授權](docs/素材來源.md)
- [P2 動畫修正與驗收](docs/team/trex/p2-handoff.md)
- [五鏡頭 MP4](media/trex-forest-unity.mp4?raw=true)（Unity 6000.4.11f1 實際渲染，12.5 秒，1280×720，24 fps，無音軌）
- [成片畫格](Evidence/shot-contact.jpg)

## 開啟專案

1. 安裝 Unity 6000.4.11f1，並在 Unity Hub 登入、啟用授權。
2. Unity Hub 選 **Projects → Add → Add project from disk**，指向本 repo 根目錄。
3. 開啟 `Assets/Scenes/TRexForest.unity`。需要從來源重組時，選 **TRex → Build Forest Scene**。
4. 選 **TRex → Render Forest Smoke Test** 預覽每鏡頭起、中、末三格；選 **TRex → Render Forest Film** 輸出完整 PNG 序列。

## 分件設計

- 13 個獨立蒙皮網格，共用一副 29 骨骨架（`TRexArmature`）：Body（軀幹與頸）、Head、LowerJaw、Tail、LeftLeg、RightLeg、LeftArm、RightArm、UpperTeeth、LowerTeeth、LeftEye、RightEye、Tongue。腳爪與指爪屬於腿、臂零件，使用角質材質。
- 材質槽 `TRexSkin`、`TRexTeeth`、`TRexEye`、`TRexMouth`，貼圖位於 `Assets/Source/Textures/<槽名>/`。分件 Mesh 資產在 `Assets/Generated/DinosaurParts/`，Prefab 在 `Assets/Generated/Prefabs/`。
- 動作：`Walk`（2 秒循環）、`Run`（1 秒循環）、`HeadShake`、`Roar`（2.5 秒，下顎張開約 36°）。腿部以解析式雙骨 IK 求解，原地循環；場景位移依腳步著地速度設定，FBX 著地殘餘位移見 P2 驗收。
- P2 修正：擺動腳趾向上抬、腳部預留 2 cm 蒙皮間距、走路抬跟角度 18°，雙臂反相。動作曲線以每秒 192 次取樣烘焙，場景與影片仍為 24 fps。

## 重建模型

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b --factory-startup --python-exit-code 1 --python .\Tools\build_trex.py -- --preview .\Render\preview --poses
```

這段指令會重寫 `Assets/Source/Dinosaur/TRex.fbx`、`Assets/Source/Textures/TRex*/` 和 `Evidence/trex-asset-check.json`，並在乾淨場景中重新匯入 FBX，驗證零件、骨架與動作。建模參數集中在 `Tools/trex/` 底下：`geometry.py` 管輪廓與零件，`rig.py` 管骨架與權重，`anim.py` 管動作，`textures.py` 管材質與烘焙。

動畫回歸檢查（實際腳部蒙皮、雙臂反相、循環接縫、求解器與烘焙後的著地防滑）：

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b --factory-startup --python-exit-code 1 --python .\Tools\test_trex_motion.py
```

## 批次渲染

```powershell
$unityExe = 'C:\Program Files\Unity\Hub\Editor\6000.4.11f1\Editor\Unity.exe'
& .\Tools\Render-UnityForest.ps1 -UnityExe $unityExe -Smoke -Width 640 -Height 360
& .\Tools\Render-UnityForest.ps1 -UnityExe $unityExe
```
