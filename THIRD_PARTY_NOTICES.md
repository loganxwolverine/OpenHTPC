# Third-party notices

OPENHTPC Core code is licensed separately under Apache-2.0 in `LICENSE`.
Third-party components below retain their own licenses.

| Component | Upstream | License | Distributed files | Full license |
|---|---|---|---|---|
| Flex Launcher | `complexlogic/flex-launcher`, commit `94a7a273fe8124df51e63058816526b66bbc9538` | The Unlicense | `payload/flex/bin/flex-launcher`, Flex icons; qualified OPENHTPC dev27 adaptation | `third_party/licenses/Flex-Launcher-UNLICENSE.txt` |
| NanoSVG / NanoSVGRast | `memononen/nanosvg` | zlib | Incorporated into the Flex Launcher binary | `third_party/licenses/NanoSVG-zlib.txt` |
| Open Sans Regular | Open Sans project | SIL Open Font License 1.1 | `payload/flex/assets/fonts/OpenSans-Regular.ttf` | `third_party/licenses/OFL-1.1.txt` |
| Anime4K shaders | `bloc97/Anime4K` and per-file upstream authors | MIT or Unlicense as declared in each header | `payload/assets/shaders/Anime4K_*` | Individual headers; `third_party/licenses/MIT.txt`, `third_party/licenses/Unlicense.txt` |
| ArtCNN shaders | `Artoriuz/ArtCNN` | MIT | `payload/assets/shaders/ArtCNN_*` | Individual headers; `third_party/licenses/MIT.txt` |
| CfL Prediction | `Artoriuz/glsl-chroma-from-luma-prediction` | MIT | `payload/assets/shaders/CfL_*` | Individual headers; `third_party/licenses/MIT.txt` |
| FidelityFX Super Resolution GLSL port | AMD FidelityFX FSR; GLSL port provenance retained in file | MIT | `payload/assets/shaders/FSR.glsl` | File header; `third_party/licenses/MIT.txt` |
| FSRCNNX | `igv/FSRCNN-TensorFlow` / mpv shader distribution | LGPL-3.0-or-later | `payload/assets/shaders/FSRCNNX_*` | Individual headers; `third_party/licenses/LGPL-3.0.txt` |
| KrigBilateral | Shiandow mpv shader | LGPL-3.0-or-later | `payload/assets/shaders/KrigBilateral.glsl` | File header; `third_party/licenses/LGPL-3.0.txt` |
| RAVU | `bjin/mpv-prescalers` | LGPL-3.0 | `payload/assets/shaders/ravu-*.hook` | Individual headers; `third_party/licenses/LGPL-3.0.txt` |
| SSimDownscaler / SSimSuperRes | igv mpv shaders | LGPL-3.0-or-later | `payload/assets/shaders/SSim*.glsl` | Individual headers; `third_party/licenses/LGPL-3.0.txt` |
| adaptive-sharpen | bacondither / igv shader port | BSD-2-Clause | `payload/assets/shaders/adaptive-sharpen.glsl` | File header; `third_party/licenses/BSD-2-Clause.txt` |

The Open Sans binary retains its embedded upstream naming and copyright
metadata. It is redistributed unmodified under OFL-1.1.

`filmgrain.glsl` from `deus0ww/mpv-conf` is intentionally not distributed
because redistribution terms were not established. It is not referenced by the
qualified recipe or calibration catalogues distributed in R2.

The synthetic benchmark videos are original OPENHTPC test patterns; see
`assets/ASSET_PROVENANCE.md` and `payload/assets/benchmark/manifest.json`.
