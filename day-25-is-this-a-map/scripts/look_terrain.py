"""Quick look at the terrain render: flat night sky behind, aerial perspective from the depth pass, simple tone curve.
Writes renders/terrain_haze_look.png (1080) and two full-res horizon crops. Also packs renders/terrain_2160.npz."""
import numpy as np, OpenEXR
from PIL import Image
from common import *
n = 2160
T = list(OpenEXR.File(str(RENDERS / "terrain_2160.exr")).parts[0].channels.values())[0].pixels
D = list(OpenEXR.File(str(RENDERS / "depth_2160.exr")).parts[0].channels.values())[0].pixels
rgb, a = T[..., :3], T[..., 3]
dkm = D[..., 0] / np.maximum(D[..., 3], 1e-6)
np.savez_compressed(RENDERS / "terrain_2160.npz", rgb=rgb.astype(np.float32), alpha=a.astype(np.float32), depth_km=dkm.astype(np.float32))
yy, xx = np.mgrid[0:n, 0:n]; z = np.hypot(xx - n / 2 + .5, yy - n / 2 + .5) / (n / 2) * 105; inside = z <= 105
sky = 10 ** ((12.58 - SQM_ZENITH) / 2.5)
Tr = np.exp(-0.025 * dkm)[..., None]
G = rgb * Tr + sky * 2.5 * (1 - Tr) * np.array([0.9, 1, 1.05])
cz = np.cos(np.radians(np.clip(z, 0, 89.5))); X = 1 / (cz + 0.025 * np.exp(-11 * cz))
skyL = (sky * (0.45 + 0.55 * np.minimum(X, 12) ** 0.7))[..., None]
lin = (G * a[..., None] + skyL * (1 - a[..., None])) * inside[..., None]
x = lin / sky * 0.12; img = (x / (1 + x)) ** (1 / 2.2)
u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
Image.fromarray(u8).resize((1080, 1080), Image.LANCZOS).save(RENDERS / "terrain_haze_look.png")
Image.fromarray(u8[1880:2100, 600:1560]).save(RENDERS / "terrain_haze_south_crop.png")
Image.fromarray(u8[60:300, 500:1500]).save(RENDERS / "terrain_haze_north_crop.png")
print("ok")
