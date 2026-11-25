"""Compose the sky circle: terrain (Blender) + natural sky + artificial skyglow + Milky Way (Gaia) + stars +
planets, summed in linear luminance (cd/m^2), one tone curve, constellation lines.

python3 07_compose.py [seconds_after_2300]   -> renders/sky_<s>.png (circle on black, 1080 x 1350) and
                                                renders/sky_<s>_circle.npy (tone-mapped circle, for 08_poster.py)
"""
import json, sys, importlib, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import map_coordinates
from common import *

sky = importlib.import_module("05_sky")

W, H = 1080, 1350
D = 1040                                   # sky circle diameter (px); rim = 105 deg from the zenith
CX, CY = W / 2, H - 20 - D / 2             # circle centre in the frame
FOV_HALF = 105.0
DEG_PX = FOV_HALF / (D / 2)                # 0.202 deg per px
PIX_SR = math.radians(DEG_PX) ** 2

L_NAT = 10 ** ((12.58 - 22.0) / 2.5)                     # natural zenith (cd/m^2), 22.0 mag/arcsec^2
L_ART = ARTIF_RATIO * L_NAT                              # artificial zenith (Falchi atlas ratio 1.58)
LUX_V0 = 2.54e-6                                         # illuminance of a V = 0 star (lux)
K_EXT = 0.20                                             # V-band extinction (mag per airmass) at 1.9 km
BETA0_KM, H_AER_KM = 0.10, 1.2                           # aerosol extinction at sea level (1/km) and its scale height
BETA_R0_KM, H_R_KM = 0.0116, 8.0                         # Rayleigh extinction (550 nm) at sea level and scale height
HALO_FRAC = 0.15                                         # share of the light scattered out of a town that stays near it
LIGHT_GAIN = 0.35                                        # display choice: town lights x0.35 on top of emission direction + haze
PSF_SIGMA = 0.7                                          # px

# --------------------------------------------------------------------------- pixel geometry (circle grid)
yy, xx = np.mgrid[0:D, 0:D] + 0.5
dx, dy = xx - D / 2, yy - D / 2
ZEN = np.hypot(dx, dy) * DEG_PX                          # zenith distance
AZ = np.degrees(np.arctan2(-dx, -dy)) % 360              # north up, east left
ALT = 90 - ZEN
INSIDE = ZEN <= FOV_HALF


def airmass(z):
    cz = np.cos(np.radians(np.clip(z, 0, 89.5)))
    return np.minimum(1 / (cz + 0.025 * np.exp(-11 * cz)), 12)


def natural_sky():
    """Airglow + scattered starlight: 22.0 at the zenith, brightening with airmass (van Rhijn-like)."""
    return L_NAT * (0.45 + 0.55 * airmass(ZEN) ** 0.7)


def artificial_sky():
    """Skyglow from every VIIRS source within 130 km (2 km cells), weighted I d^-2.5, with a dome that is strong
    low in the source's direction and weak overhead; scaled so the zenith equals the Falchi atlas value."""
    L = np.load(DERIVED / "lights100.npy").astype(np.float64)
    n = L.shape[0] // 20 * 20
    Lb = L[:n, :n].reshape(n // 20, 20, n // 20, 20).sum((1, 3))
    half = RINGS[2][1]; c = (np.arange(n // 20) + 0.5) * 2000 - half
    X, Y = np.meshgrid(c, -c)
    m = (Lb > 0) & (np.hypot(X, Y) > 1500)
    I, x, y = Lb[m], X[m], Y[m]
    d = np.hypot(x, y) / 1000; saz = np.degrees(np.arctan2(x, y)) % 360
    w = I * d ** -2.5
    az_g, alt_g = np.arange(0, 360, 2.0), np.arange(-16, 91, 1.0)
    G = np.zeros((alt_g.size, az_g.size))
    for i, a in enumerate(alt_g):
        aa = max(a, 0)
        daz = (az_g[:, None] - saz[None, :] + 180) % 360 - 180
        width = 20 + 60 * np.exp(-d / 15)                # nearby cities make wider domes
        dome = np.exp(-0.5 * (daz / width) ** 2) * np.exp(-aa / (6 + 0.4 * aa)) * 6
        G[i] = ((0.3 + dome) * w).sum(1)
    G /= G[-1].mean()                                    # zenith = 1
    gi = map_coordinates(G, [np.clip(ALT, -16, 90) - alt_g[0], AZ / 2.0], order=1, mode="wrap")
    return L_ART * gi, (G, az_g, alt_g), np.clip(1 - 1 / np.maximum(gi, 1e-6), 0, 1)


def load_terrain():
    """Blender terrain (2160 px circle) resampled to the D px circle by area averaging."""
    T = np.load(RENDERS / "terrain_2160.npz")
    rgb, a, dkm = T["rgb"], T["alpha"], T["depth_km"]
    n = rgb.shape[0]
    f = n / D
    out = []
    for ch in [rgb[..., 0] * a, rgb[..., 1] * a, rgb[..., 2] * a, a, np.where(a > 0, dkm, 0) * a]:
        im = Image.fromarray(ch.astype(np.float32), mode="F").resize((D, D), Image.BOX)
        out.append(np.asarray(im, np.float64))
    r, g, b, alpha, dsum = out
    alpha = np.clip(alpha, 0, 1) * INSIDE
    depth = np.where(alpha > 1e-3, dsum / np.maximum(alpha, 1e-3), 0)
    prem = np.stack([r, g, b], -1)
    return prem, alpha, depth


# ICRS -> galactic (IAU 1958 / J2000 values)
_GAL = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
                 [+0.4941094279, -0.4448296300, +0.7469822445],
                 [-0.8676661490, -0.1980763734, +0.4559837762]])
MW_TARGET_MAG = 21.5          # mag/arcsec^2 of the Milky Way near Cygnus (l = 75 deg, b = 0)
MW_DEX = 1.4                  # dynamic range of the band: poles to Sagittarius star clouds, in log10 luminance
_MW = None


def _mw_texture():
    """Gaia DR2 'sky in colour' (log-scaled flux, sRGB). Point sources removed (median 5x5 at 0.045 deg/px; the
    catalogue stars are drawn separately), shrunk to 4000 x 2000, then turned into linear luminance: the
    image's log scale is mapped to MW_DEX decades and calibrated so Cygnus is MW_TARGET_MAG."""
    from scipy.ndimage import median_filter
    im = np.asarray(Image.open(DERIVED / "gaia_dr2_8000x4000.png").convert("RGB"), np.float32) / 255
    im = np.stack([median_filter(im[..., c], 5) for c in range(3)], -1)
    im = np.asarray(Image.fromarray((im * 255).astype(np.uint8)).resize((4000, 2000), Image.BOX), np.float32) / 255
    Y = im.mean(-1)
    lo, hi = np.percentile(Y, 2), np.percentile(Y, 99.9)
    lin_Y = 10 ** (MW_DEX * (np.clip(Y, lo, hi) - hi) / (hi - lo))          # 1 at the brightest
    lin_Y -= lin_Y.min()                                                     # dark sky between stars -> 0
    chroma = im / np.maximum(Y[..., None], 1e-3)
    chroma = 1 + 0.6 * (chroma - 1)                                          # mild desaturation
    # calibrate on Cygnus (l = 75, b = 0): mean over a 3 x 3 deg box
    Hh, Ww = Y.shape
    def px(l, b):
        l = (l + 180) % 360 - 180
        return int((0.5 - l / 360) * Ww), int((0.5 - b / 180) * Hh)
    cx, cy = px(75, 0); k = int(1.5 / 360 * Ww)
    scale = 10 ** ((12.58 - MW_TARGET_MAG) / 2.5) / lin_Y[cy - k:cy + k, cx - k:cx + k].mean()
    return (lin_Y[..., None] * chroma * scale).astype(np.float32)


def milky_way(t, half=True):
    """Per-pixel lookup: local (east, north, up) -> ICRS -> galactic -> texture. Computed at half resolution."""
    global _MW
    f = DERIVED / "gaia_dr2_8000x4000.png"
    if not f.exists():
        return None
    if _MW is None:
        _MW = _mw_texture()
    M = sky.radec_to_altaz_matrix(t)                  # ICRS -> ENU
    n = D // 2 if half else D
    yy_, xx_ = np.mgrid[0:n, 0:n] + 0.5
    s_ = D / n
    dx_, dy_ = xx_ * s_ - D / 2, yy_ * s_ - D / 2
    zen = np.radians(np.hypot(dx_, dy_) * DEG_PX); az = np.arctan2(-dx_, -dy_)
    enu = np.stack([np.sin(zen) * np.sin(az), np.sin(zen) * np.cos(az), np.cos(zen)], -1)
    icrs = enu @ np.linalg.inv(M).T
    g = icrs @ _GAL.T
    l = np.degrees(np.arctan2(g[..., 1], g[..., 0])); b = np.degrees(np.arcsin(np.clip(g[..., 2], -1, 1)))
    Hh, Ww = _MW.shape[:2]
    xs = ((0.5 - l / 360) * Ww) % Ww - 0.5; ys = (0.5 - b / 180) * Hh - 0.5
    out = np.stack([map_coordinates(_MW[..., c], [ys, xs], order=1, mode="wrap") for c in range(3)], -1)
    # extinction with airmass, like the stars
    out *= 10 ** (-0.4 * K_EXT * (airmass(np.degrees(zen)) - 1))[..., None]
    if half:
        out = np.stack([np.asarray(Image.fromarray(out[..., c].astype(np.float32), mode="F").resize((D, D), Image.BILINEAR)) for c in range(3)], -1)
    return out


def splat(buf, x, y, lum_total, rgb, sigma=PSF_SIGMA):
    """Add Gaussian PSFs (integral = lum_total, in cd/m^2 x px) at sub-pixel positions."""
    k = int(math.ceil(3.5 * sigma))
    oy, ox = np.mgrid[-k:k + 1, -k:k + 1]
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - ix - 0.5, y - iy - 0.5
    ok = (ix >= k) & (ix < D - k) & (iy >= k) & (iy < D - k)
    ix, iy, fx, fy, lum_total, rgb = ix[ok], iy[ok], fx[ok], fy[ok], lum_total[ok], rgb[ok]
    g = np.exp(-((ox[None] - fx[:, None, None]) ** 2 + (oy[None] - fy[:, None, None]) ** 2) / (2 * sigma ** 2))
    g /= g.sum((1, 2), keepdims=True)
    for c in range(3):
        np.add.at(buf[..., c], (iy[:, None, None] + oy[None], ix[:, None, None] + ox[None]),
                  g * (lum_total * rgb[:, c])[:, None, None])


def project(alt, az):
    r = (90 - alt) / DEG_PX
    a = np.radians(az)
    return D / 2 - r * np.sin(a), D / 2 - r * np.cos(a)


def bv_rgb(bv):
    T = 4600 * (1 / (0.92 * bv + 1.7) + 1 / (0.92 * bv + 0.62))   # Ballesteros 2012
    t = np.clip(T / 6500, 0.5, 2.0)
    c = np.stack([t ** -0.9, np.ones_like(t), t ** 1.1], -1)
    c /= c.mean(1, keepdims=True)
    return 0.6 + 0.4 * c                                            # ~40% saturation


def star_layer(t):
    buf = np.zeros((D, D, 3))
    alt, az = sky.stars_altaz(t)
    V = sky.CAT["vmag"] + K_EXT * (airmass(90 - alt) - 1)
    m = (alt > -1) & (V < 8)
    x, y = project(alt[m], az[m])
    lum = LUX_V0 * 10 ** (-0.4 * V[m]) / PIX_SR                     # cd/m^2 x px (integral over the PSF)
    rgb = bv_rgb(sky.CAT["bv"][m])
    # planets above the horizon
    from skyfield.magnitudelib import planetary_magnitude
    px, py, pl, pc = [], [], [], []
    for p, col in [("saturn barycenter", [1.05, 1.0, 0.85]), ("neptune barycenter", [0.8, 0.9, 1.1])]:
        a, z = sky.altaz(sky.eph[p], t)
        if a > -1:
            mag = float(planetary_magnitude(sky.site.at(t).observe(sky.eph[p])))
            mag += K_EXT * (float(airmass(np.array(90 - a))) - 1)
            xx_, yy_ = project(np.array([a]), np.array([z])); px += [xx_[0]]; py += [yy_[0]]
            pl += [LUX_V0 * 10 ** (-0.4 * mag) / PIX_SR]; pc += [col]
    if px:
        x = np.r_[x, px]; y = np.r_[y, py]; lum = np.r_[lum, pl]; rgb = np.r_[rgb, pc]
    splat(buf, x, y, lum, rgb)
    return buf


# --------------------------------------------------------------------------- constellation lines
# d3-celestial constellations.lines.json (c) 2015 Olaf Frohn, BSD 3-Clause. Coordinates: [RA deg (-180..180), Dec].
LINE_ALPHA = 0.15          # white at 15%, 1 px
LINE_TRIM_DEG = 0.9        # gap at each star so the line does not run into it
LINE_STEP_DEG = 0.5


def _constellation_points():
    feats = json.load(open(RAW / "constellations.lines.json"))["features"]
    ra, dec, seg = [], [], []
    k = 0
    for f in feats:
        for line in f["geometry"]["coordinates"]:
            for (a0, d0), (a1, d1) in zip(line[:-1], line[1:]):
                v0 = np.array([math.cos(math.radians(d0)) * math.cos(math.radians(a0)), math.cos(math.radians(d0)) * math.sin(math.radians(a0)), math.sin(math.radians(d0))])
                v1 = np.array([math.cos(math.radians(d1)) * math.cos(math.radians(a1)), math.cos(math.radians(d1)) * math.sin(math.radians(a1)), math.sin(math.radians(d1))])
                ang = math.degrees(math.acos(np.clip(np.dot(v0, v1), -1, 1)))
                if ang < 2.5 * LINE_TRIM_DEG:
                    continue
                f_ = np.linspace(LINE_TRIM_DEG / ang, 1 - LINE_TRIM_DEG / ang, max(2, int(ang / LINE_STEP_DEG)))
                A = math.radians(ang)
                v = (np.sin((1 - f_) * A)[:, None] * v0 + np.sin(f_ * A)[:, None] * v1) / math.sin(A)
                ra += list(np.degrees(np.arctan2(v[:, 1], v[:, 0])) % 360); dec += list(np.degrees(np.arcsin(v[:, 2])))
                seg += [k] * len(f_); k += 1
    from skyfield.api import Star
    return Star(ra_hours=np.array(ra) / 15, dec_degrees=np.array(dec)), np.array(seg)


_CL = None


def draw_constellations(circle_rgb, t, alpha_terrain):
    """Lines on the tone-mapped circle, in sky coordinates (bent by the lens), hidden behind terrain."""
    global _CL
    if _CL is None:
        _CL = _constellation_points()
    stars, seg = _CL
    alt, az = sky.altaz(stars, t)
    x, y = project(alt, az)
    SS = 3
    layer = Image.new("L", (D * SS, D * SS), 0); dr = ImageDraw.Draw(layer)
    for k in np.unique(seg):
        m = seg == k
        if (alt[m] < -2).all():
            continue
        pts = list(zip((x[m] * SS).tolist(), (y[m] * SS).tolist()))
        dr.line(pts, fill=255, width=SS)
    a = np.asarray(layer.resize((D, D), Image.BOX), np.float64) / 255 * LINE_ALPHA
    a *= (1 - alpha_terrain) * INSIDE
    return circle_rgb * (1 - a[..., None]) + a[..., None]


def tone(lin, ref):
    """One fixed log-contrast curve, u = log10(L / zenith sky): black at u = -1.2, white at +2.6, power 2.0,
    soft shoulder. The zenith sky lands at ~40/255; terrain (0.12 x sky plus haze) stays just above black."""
    u = np.log10(np.maximum(lin, 1e-12) / ref)
    s = np.clip((u + 1.2) / 3.8, 0, 1)
    y = s ** 2.0
    return y / (y + (1 - y) * 0.6)


class Composer:
    def __init__(self):
        self.nat = natural_sky()
        self.art, (self.G, self.az_g, self.alt_g), self.warm = artificial_sky()
        # natural: neutral, slightly green (airglow). Artificial: near-neutral where it is the diffuse overhead part
        # (Rayleigh-scattered), warm (sodium + LED) where it is the dome low over the towns.
        art_rgb = (1 - self.warm[..., None]) * np.array([0.95, 1.0, 1.02]) + self.warm[..., None] * np.array([1.25, 1.0, 0.65])
        self.sky = self.nat[..., None] * np.array([0.92, 1.0, 0.98]) + self.art[..., None] * art_rgb
        prem, alpha, depth = load_terrain()
        # split the ground into sky-lit rock (albedo 0.12 x sky, at most) and emitted town light
        base = 0.12 * 10 ** ((12.58 - SQM_ZENITH) / 2.5) * alpha[..., None]
        rock = np.minimum(prem, base); emit = np.maximum(prem - base, 0) * LIGHT_GAIN
        # extinction along each sightline: aerosol (H = 1.2 km) + Rayleigh (H = 8 km), integrated between the
        # eye and the target's altitude; the target's altitude comes from its depth and elevation angle
        dkm = np.maximum(depth, 1e-3)
        h0 = (GROUND + EYE) / 1000
        h1 = h0 + dkm * np.tan(np.radians(np.clip(ALT, -60, 30))) + drop(dkm * 1000) / 1000
        def tau(beta0, H):
            dh = h1 - h0
            small = np.abs(dh) < 1e-3
            with np.errstate(divide="ignore", invalid="ignore"):
                t_ = beta0 * dkm * H / dh * (np.exp(-h0 / H) - np.exp(-h1 / H))
            return np.where(small, beta0 * dkm * np.exp(-h0 / H), t_)
        Tr = np.exp(-(tau(BETA0_KM, H_AER_KM) + tau(BETA_R0_KM, H_R_KM)))[..., None]
        self.Tr = Tr
        hz = map_coordinates(self.G, [np.full_like(AZ, 0.5 - self.alt_g[0]), AZ / 2.0], order=1, mode="wrap") * L_ART \
            + L_NAT * (0.45 + 0.55 * 12 ** 0.7)
        air = hz[..., None] * np.array([0.95, 1.0, 1.02])
        self.ground = (rock + emit) * Tr + alpha[..., None] * air * (1 - Tr)
        # light scattered out of the towns' sightlines: part of it forms a halo around them
        from scipy.ndimage import gaussian_filter
        sc = emit * (1 - Tr) * HALO_FRAC
        self.halo = np.stack([0.6 * gaussian_filter(sc[..., c], 2.5) + 0.4 * gaussian_filter(sc[..., c], 9) for c in range(3)], -1)
        self.alpha = alpha
        self.ref = L_NAT + L_ART
        self.lines = True
        self.font = ImageFont.truetype(str(RAW / "Inter.ttf"), 22)
        self.font.set_variation_by_axes([14, 500]) if hasattr(self.font, "set_variation_by_axes") else None

    def circle(self, t, still_t):
        """Tone-mapped sky circle (D x D x 3, 0..1) and the terrain alpha."""
        upper = self.sky + star_layer(t)
        mw = milky_way(t)
        if mw is not None:
            upper = upper + mw
        lin = upper * (1 - self.alpha[..., None]) + self.ground + self.halo
        lin *= INSIDE[..., None]
        img = tone(lin, self.ref)
        if self.lines:
            img = draw_constellations(img, t, self.alpha)
        return np.clip(img, 0, 1) * INSIDE[..., None]

    def frame(self, t, still_t):
        circle = (self.circle(t, still_t) * 255 + 0.5).astype(np.uint8)
        frame = Image.new("RGB", (W, H), (0, 0, 0))
        frame.paste(Image.fromarray(circle), (int(CX - D / 2), int(CY - D / 2)), Image.fromarray((INSIDE * 255).astype(np.uint8)))
        return frame


if __name__ == "__main__":
    s_ = float(sys.argv[1]) if len(sys.argv) > 1 else 3044
    C = Composer()
    t = sky.ts.utc(2026, 8, 12, 21, 0, s_)
    circ = C.circle(t, s_)
    np.save(RENDERS / f"sky_{int(s_)}_circle.npy", circ.astype(np.float32))
    C.frame(t, s_).save(RENDERS / f"sky_{int(s_)}.png")
    print("saved", RENDERS / f"sky_{int(s_)}.png")
