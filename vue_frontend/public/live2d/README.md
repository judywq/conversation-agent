# Live2D assets (not committed)

These files are covered by the Live2D Proprietary License (Cubism Core) and the
Live2D Free Material License (sample models) and must not be redistributed via
this repository. To set up locally:

1. `live2dcubismcore.min.js` — download directly from
   `https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js`
   (or via the Cubism SDK for Web at https://www.live2d.com/sdk/download/web/,
   `Core/live2dcubismcore.min.js`) and copy it here.
2. Sample models — fetch the `Hiyori`, `Haru`, `Mao`, `Natori` folders from
   `https://github.com/Live2D/CubismWebSamples` (`Samples/Resources/<Name>/`,
   e.g. via `git clone --filter=blob:none --sparse` + `git sparse-checkout set`)
   and place each folder's contents under `public/live2d/<name>/` so the
   manifest lives at `public/live2d/<name>/<Name>.model3.json` with its
   `.moc3`, textures, `.physics3.json`, `.pose3.json`, `.cdi3.json`, and
   `motions/`/`expressions/` alongside it (paths inside the manifest are
   relative, so keep the folder layout intact):
   - hiyori, haru, mao (female presets), natori (male preset)
3. Model URLs are wired in `src/config/avatarPresets.ts` — update filenames there if
   the source ships different manifest names.

Sample models © Live2D Inc., used under the Live2D Free Material License
(https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html).
