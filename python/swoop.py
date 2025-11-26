# swoop.py
import pygame
import csv
import os
import argparse
import math
import random 

# -------------------------- Output logging -------------------------------

RESULTS_DIR = "output"
RESULTS_CSV = "results_swoop.csv"

# --------------------------- Global scale --------------------------------
# Master scaling for distances and pixel rates.
#   GLOBAL_SCALE < 1.0  → "zoomed out" (things are closer/tighter, slower)
#   GLOBAL_SCALE = 1.0  → current behaviour
#   GLOBAL_SCALE > 1.0  → "zoomed in" (things are further/spread, faster)
GLOBAL_SCALE = 0.6
BIRD_BASE_SCALE = 0.1   # original "shrink about 10x"

# Fraction of outer radius that defines "too late" inner boundary
RESPONSE_INNER_FRACTION = 1/3   # 0.5 = half-radius; change to 0.6, 0.7, etc.

# Separation radius between THREAT and SAFE miss ranges (base = 50 px)
SEP_RADIUS_PX_BASE = 50
SEP_RADIUS_PX      = int(SEP_RADIUS_PX_BASE * GLOBAL_SCALE)

# ---------------------------- Defaults -----------------------------------
  
SCREEN_WIDTH  = 1280
SCREEN_HEIGHT = 720
FPS           = 60
  
BG_COLOR         = (10, 10, 10)       # darker backdrop outside sensor
SECTOR_COLOR = (20, 50, 25)
# Phosphor green with transparency for inner radial circle
# INNER_RADIUS_COLOR = (120, 255, 140, 150)  # RGBA (alpha = 150)
# Red inner radial ring with transparency (same alpha)
# INNER_RADIUS_COLOR = (255, 80, 80, 150)  # RGBA (alpha = 150)
INNER_RADIUS_COLOR = (255, 220, 120, 150) # "TOO SLOW!" yellow
# INNER_RADIUS_COLOR = (255, 0, 0, 150) # laser red

CIRCLE_COLOR     = (120, 255, 140)     # phosphor green ownship circle
TEXT_COLOR       = (120, 255, 140)    # off-white
CIRCLE_RADIUS    = int(10 * GLOBAL_SCALE)   # scaled ownship radius

# ------------------------- Ownship controls ------------------------------

OWN_BRG_STEP_DEG   = 1.0    # degrees per left/right key press
OWN_SPD_STEP_KT    = 1.0    # knots per up/down key press
OWN_SPD_MIN_KT     = 0.0    # no reverse for now
OWN_SPD_MAX_KT     = 1000.0  # arbitrary cap
# Continuous change when keys are held (per second)
OWN_BRG_RATE_DEG_PER_SEC  = 60.0   # deg/s while held
OWN_SPD_RATE_KT_PER_SEC   = 80.0   # kt/s while held



# # ------------------------ Ground layer (static) ---------------------------
# 
# NUM_GROUND_SPECKS   = 800             # density
# 
# # Ocean foam palette: cool whites / pale seafoam
# GROUND_COLOR        = (190, 230, 240)   # soft seafoam base
# GROUND_HIGHLIGHT    = (245, 250, 255)   # bright white foam
# GROUND_SHADOW       = (150, 190, 210)   # slightly darker wet patches
# GROUND_ALPHA        = 180               # a bit more solid

  
# ------------------------- Wind layer (turbulent) -------------------------

NUM_WIND_SPECKS     = 2000             # density
  
# Wind layer visual properties (uniform)
WIND_RADIUS         = max(1, int(round(3 * GLOBAL_SCALE)))
# Soft summery pollen palette (warm yellow/white)
WIND_COLOR_DARK     = (220, 200, 70)   # deeper pollen yellow
WIND_COLOR_LIGHT    = (255, 250, 220)  # pale creamy pollen/white

WIND_ALPHA = 140               # slightly more visible (optional)
  
# How fast the wind field scrolls per knot of speed (pixels/sec/knot)
WINDFIELD_PX_PER_KT = 1.0 * GLOBAL_SCALE
  
# ---------------------- Prevailing wind random walk ----------------------
  
WIND_INIT_SPEED_KT    = 100.0   # initial prevailing wind speed
WIND_INIT_BEARING_DEG = 180.0   # initial prevailing wind bearing (0=N, 90=E)
  
WIND_SPEED_MIN_KT    = 100.0
WIND_SPEED_MAX_KT    = 500.0
  
# Random-walk strengths (per second, used as Lévy scales)
WIND_SPEED_RW_STD    = 2.5      # ~typical speed step size (knots)
WIND_BEARING_RW_STD  = 10.0      # ~typical bearing step size (degrees)
  
# How often to update wind (seconds)
WIND_UPDATE_INTERVAL = 1.0 / 3.0   # 3 times per second
  
# How much each component contributes to wind-layer scrolling
WIND_LAYER_OWNSHIP_WEIGHT = 0.5
WIND_LAYER_WIND_WEIGHT    = 1 - WIND_LAYER_OWNSHIP_WEIGHT
  
# ----------------------------- Compass HUD --------------------------------
  
COMPASS_RADIUS     = int(70 * GLOBAL_SCALE)
COMPASS_MARGIN_X   = 40   # distance from right edge
COMPASS_LINE_COLOR = (240, 240, 240)  # same as TEXT_COLOR
COMPASS_BG_COLOR   = (0, 0, 0)        # black circle background
COMPASS_RING_COLOR = (80, 80, 80)     # outer ring


# ------------------------- Ownship vectors -------------------------------

THRUST_VECTOR_COLOR = (255, 220, 120)   # warm yellow-ish (forward / thrust)
DRAG_VECTOR_COLOR   = (160, 220, 255)   # cool cyan-ish (rearward / drag)
COMP_EW_COLOR       = (120, 255, 180)   # E–W component
COMP_NS_COLOR       = (255, 150, 200)   # N–S component

THRUST_VECTOR_PX_PER_KT = 0.3 * GLOBAL_SCALE  # pixels of vector length per knot
VECTOR_LINE_WIDTH       = 1
COMP_VECTOR_LINE_WIDTH  = 1

# ------------------------------ Intruder ---------------------------------

INTRUDER_COLOR        = (255, 120, 120)  # warm red-ish to pop against sea
INTRUDER_RADIUS       = int(10 * GLOBAL_SCALE)
INTRUDER_PX_PER_KT    = THRUST_VECTOR_PX_PER_KT  # same scale as vectors
INTRUDER_HEADING_LEN  = int(10 * GLOBAL_SCALE)   # small nose line to show heading



# ---------------------------- CSV loading --------------------------------
  
def load_ownship_from_csv(path):
    """
    Read a single-row CSV with:
      - ownship_speed      : ownship speed in knots
      - ownship_bearing    : ownship heading in degrees
      - x_dim, y_dim       : screen size (pixels)
      - DOMS               : min separation vs intruder (NM)
      - TTMS               : time to min sep (s)
      - speed_intr_kn      : intruder speed (knots)
      - bearing_intr_deg   : intruder heading (deg, 0=N, 90=E)
      - intruder_x_px      : intruder start x (pixels)
      - intruder_y_px      : intruder start y (pixels)

    Optionally, x_px / y_px can be given for ownship; otherwise we
    default ownship to the centre of the screen.

    Returns (ownship, intruder, screen_w, screen_h).
    """
    global SCREEN_WIDTH, SCREEN_HEIGHT

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)  # first row only

    def parse_float(row, key, default=None):
        if key in row and str(row[key]).strip() != "":
            return float(row[key])
        return default

    # Screen dimensions
    x_dim = parse_float(row, "x_dim", default=SCREEN_WIDTH)
    y_dim = parse_float(row, "y_dim", default=SCREEN_HEIGHT)

    SCREEN_WIDTH  = int(x_dim)
    SCREEN_HEIGHT = int(y_dim)

    # Ownship position (optional; default to screen centre)
    x = parse_float(row, "x_px", default=SCREEN_WIDTH  / 2.0)
    y = parse_float(row, "y_px", default=SCREEN_HEIGHT / 2.0)

    # Ownship kinematics
    speed_kn    = parse_float(row, "ownship_speed",   default=None)
    bearing_deg = parse_float(row, "ownship_bearing", default=None)

    ownship = {
        "x_px": x,
        "y_px": y,
        "speed_kn": speed_kn,
        "bearing_deg": bearing_deg,
    }

    # Conflict geometry & intruder fields from the CSV
    doms   = parse_float(row, "DOMS",            default=None)
    ttms   = parse_float(row, "TTMS",            default=None)
    s_intr = parse_float(row, "speed_intr_kn",   default=None)
    b_intr = parse_float(row, "bearing_intr_deg", default=None)
    ix     = parse_float(row, "intruder_x_px",   default=None)
    iy     = parse_float(row, "intruder_y_px",   default=None)

    intruder = None
    if ix is not None and iy is not None:
        intruder = {
            "x_px": ix,
            "y_px": iy,
            "speed_kn": s_intr,
            "bearing_deg": b_intr,
            "DOMS": doms,
            "TTMS": ttms,
        }

    return ownship, intruder, SCREEN_WIDTH, SCREEN_HEIGHT

  

# --------------------------- Lévy-flight helper ---------------------------

def levy_step(scale, dt, alpha=1.5, max_step=None):
    """
    Symmetric heavy-tailed step ~ Lévy-like.
    - scale: base step size (interpreted per second)
    - dt   : time increment (seconds)
    - alpha: tail index (1 < alpha < 3; smaller = heavier tails)
    - max_step: optional clamp on absolute step size
    """
    # Uniform(0, 1), avoid exactly 0
    u = max(1e-8, random.random())

    # Positive heavy-tailed magnitude via Pareto-like transform
    # Typical magnitude ~ scale, with occasional large bursts
    mag = scale * (u ** (-1.0 / alpha) - 1.0)

    # Time scaling for Lévy process: dt^(1/alpha)
    mag *= dt ** (1.0 / alpha)

    # Random sign for symmetric steps
    if random.random() < 0.5:
        mag = -mag

    # Optional clamp
    if max_step is not None:
        if mag > max_step:
            mag = max_step
        elif mag < -max_step:
            mag = -max_step

    return mag


# ------------------------------ Drawing ----------------------------------
  
def draw_text(screen, font, text, color, center, antialias=True):
    surf = font.render(text, antialias, color)
    rect = surf.get_rect(center=center)
    screen.blit(surf, rect)
    
    
def jitter_alpha(base_alpha, low=0.6, high=1.0):
    """
    Apply the same random alpha jitter rule everywhere:
    alpha = base_alpha * U[low, high], clamped to [0, 255].
    """
    factor = random.uniform(low, high)
    a = int(base_alpha * factor)
    if a < 0:
        return 0
    if a > 255:
        return 255
    return a


# ------------------------- HUD plotting helpers -------------------------

def draw_bar_chart(screen, font, rect, counts, prop_correct=None):
    """
    Draw a simple bar chart of outcome proportions in the given rect.

    counts: dict with keys "HIT", "MISS", "NR", "FA", "CR".
    Y-axis is fixed from 0 to 1.

    prop_correct: optional float in [0,1] giving overall proportion correct.
    If None, it will be computed from counts as:
        (HIT + CR) / (HIT + MISS + FA + CR)
    """
    x, y, w, h = rect
    total = sum(counts.values())
    if total <= 0:
        # No data yet
        label = font.render("No data", True, TEXT_COLOR)
        screen.blit(label, (x + 5, y + 5))
        return

    # Background
    pygame.draw.rect(screen, (10, 10, 10), rect, 0)
    pygame.draw.rect(screen, (80, 80, 80), rect, 1)

    # Outcome order & colours
    keys = ["HIT", "MISS", "NR", "FA", "CR"]
    colors = {
        "HIT": (120, 255, 140),   # green-ish
        "MISS": (255, 120, 120),  # red-ish
        "NR": (255, 200, 120),    # amber
        "FA": (255, 160, 220),    # pink-ish
        "CR": (150, 200, 255),    # blue-ish
    }

    # --- Y-axis 0–1 ---------------------------------------------------
    axis_x = x + 5
    axis_top = y + 10
    axis_bottom = y + h - 25
    pygame.draw.line(
        screen,
        (160, 160, 160),
        (axis_x, axis_top),
        (axis_x, axis_bottom),
        1,
    )

    # Tick labels 1.0 (top) and 0.0 (bottom)
    label1 = font.render("1.0", True, TEXT_COLOR)
    label0 = font.render("0.0", True, TEXT_COLOR)
    screen.blit(
        label1,
        (axis_x + 4, axis_top - label1.get_height() // 2),
    )
    screen.blit(
        label0,
        (axis_x + 4, axis_bottom - label0.get_height() // 2),
    )

    # Y-axis label "p" above axis
    ylabel = font.render("p", True, TEXT_COLOR)
    screen.blit(
        ylabel,
        (axis_x, y - ylabel.get_height() + 5),
    )

    # ---- Bars (scaled 0–1 to axis height) ----------------------------
    bar_margin = 4
    n = len(keys)
    # Bar drawing area starts a bit to the right of the axis
    bar_area_x0 = axis_x + 30
    bar_area_width = w - (bar_area_x0 - x) - bar_margin
    if bar_area_width < 10:
        bar_area_width = max(10, w - 2 * bar_margin)

    bar_width = (bar_area_width - (n + 1) * bar_margin) / n
    max_height = axis_bottom - axis_top  # corresponds to proportion = 1

    # Draw bars
    for i, k in enumerate(keys):
        count = counts.get(k, 0)
        prop = count / total
        bh = prop * max_height

        bx = bar_area_x0 + bar_margin + i * (bar_width + bar_margin)
        by = axis_bottom - bh

        pygame.draw.rect(
            screen,
            colors.get(k, (200, 200, 200)),
            (bx, by, bar_width, bh),
        )

        # Category label under bar
        label = font.render(k, True, TEXT_COLOR)
        lr = label.get_rect(center=(bx + bar_width / 2, y + h - 8))
        screen.blit(label, lr)

    # ---- Horizontal line at overall accuracy -------------------------
    if prop_correct is None:
        # Use only scored trials: HIT, MISS, FA, CR
        scored = (
            counts.get("HIT", 0)
            + counts.get("MISS", 0)
            + counts.get("FA", 0)
            + counts.get("CR", 0)
        )
        if scored > 0:
            correct = counts.get("HIT", 0) + counts.get("CR", 0)
            prop_correct = correct / scored

    if prop_correct is not None:
        prop_correct = max(0.0, min(1.0, prop_correct))
        y_line = axis_bottom - prop_correct * max_height
        pygame.draw.line(
            screen,
            (255, 80, 80),  # red reference line
            (axis_x, int(y_line)),
            (x + w - 5, int(y_line)),
            2,
        )




def draw_rt_histogram(screen, font, rect, rts, n_bins=30, mean_rt=None):
    """
    Draw a histogram of RTs (seconds) with:
      - 30 bins
      - phosphor green bars (CIRCLE_COLOR)
      - x-axis from 0 to max(RT) with tick labels
      - x-axis label "RT (s)"
      - optional vertical red line at mean RT
    """
    x, y, w, h = rect

    # Background
    pygame.draw.rect(screen, (10, 10, 10), rect, 0)
    pygame.draw.rect(screen, (80, 80, 80), rect, 1)

    if not rts:
        label = font.render("No RTs yet", True, TEXT_COLOR)
        screen.blit(label, (x + 5, y + 5))
        return

    # RT range
    min_rt = 0.0
    max_rt = max(rts)
    if max_rt <= 0:
        max_rt = 0.001  # avoid division by zero

    # Bins
    bin_width = max_rt / n_bins
    if bin_width <= 0:
        bin_width = 1.0

    counts = [0] * n_bins
    for rt in rts:
        idx = int((rt - min_rt) / bin_width)
        if idx < 0:
            idx = 0
        if idx >= n_bins:
            idx = n_bins - 1
        counts[idx] += 1

    max_count = max(counts)
    if max_count <= 0:
        max_count = 1

    bar_margin = 2
    bar_width = (w - (n_bins + 1) * bar_margin) / n_bins
    usable_height = h - 35  # space for axis + labels

    # ---- Draw bars ----
    for i, c in enumerate(counts):
        bh = c / max_count * usable_height
        bx = x + bar_margin + i * (bar_width + bar_margin)
        by = y + (h - bh - 20)

        pygame.draw.rect(
            screen,
            CIRCLE_COLOR,  # phosphor green
            (bx, by, bar_width, bh),
        )

    # ---- Draw x-axis ----
    axis_y = y + h - 20
    x_axis_left = x + 5
    x_axis_right = x + w - 5
    pygame.draw.line(screen, (180, 180, 180),
                     (x_axis_left, axis_y), (x_axis_right, axis_y), 1)

    # Tick labels: 0 (left) and max_rt (right)
    tick0 = font.render("0", True, TEXT_COLOR)
    tick1 = font.render(f"{max_rt:.2f}", True, TEXT_COLOR)

    screen.blit(tick0, (x_axis_left, axis_y + 2))
    screen.blit(tick1, (x_axis_right - tick1.get_width(), axis_y + 2))

    # Axis label centered
    label = font.render("RT (s)", True, TEXT_COLOR)
    lr = label.get_rect(center=(x + w / 2, y + h - 5))
    screen.blit(label, lr)

    # ---- Vertical line at mean RT ------------------------------------
    if mean_rt is None and rts:
        mean_rt = sum(rts) / len(rts)

    if mean_rt is not None and max_rt > 0:
        # Clamp to [0, max_rt]
        mean_rt = max(0.0, min(max_rt, mean_rt))
        frac = mean_rt / max_rt
        x_line = x_axis_left + frac * (x_axis_right - x_axis_left)

        pygame.draw.line(
            screen,
            (255, 80, 80),  # red reference line
            (int(x_line), y + 10),
            (int(x_line), axis_y),
            2,
        )




class FloatingFeedback:
    def __init__(self, text, color, x, y, vx, vy, lifetime=1.2):
        self.text = text
        self.color = color
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.lifetime = lifetime
        self.age = 0.0

    def update(self, dt):
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        return self.age >= self.lifetime  # True = remove

    def draw(self, screen, font):
        # Render twice to make text appear heavier
        surf = font.render(self.text, True, self.color)
        rect = surf.get_rect(center=(int(self.x), int(self.y)))

        # First pass
        screen.blit(surf, rect)
        # Second pass directly on top → thicker
        screen.blit(surf, rect)



class Bird:
    """
    Sprite that spawns on the border of the circular sector, flies along a
    straight-line path that passes near the centre with a specified miss
    distance, and exits on the opposite side.

    - Miss distances are drawn ONLY from:
        THREAT: 0–40 px
        SAFE  : 60–100 px
    - Bird image is rotated so its 'top' faces the direction of travel.
    - Responses are via the keyboard:
        C = "THREAT" response
        N = "SAFE"   response

      Trial-level outcomes:
        THREAT + C (response THREAT)           = HIT
        THREAT + N (response SAFE)             = MISS
        SAFE   + C (response THREAT)           = FALSE_ALARM
        SAFE   + N (response SAFE)             = CORRECT_REJECT
        No valid OUTER-donut response by exit  = NR (non-response)

      We also log RTs for late responses (inside inner half).
    """

    THREAT_RANGE = (0.0, 40.0)   # base pixels
    SAFE_RANGE   = (60.0, 100.0) # base pixels

    def __init__(self, image_surf, screen_w, screen_h, speed_px_s=200.0):
        # Store the original upright image (facing straight up)
        self.base_image = image_surf

        self.screen_w = screen_w
        self.screen_h = screen_h
        self.speed_px_s = speed_px_s  # base speed; each trial randomises around this

        # Sector geometry: same as your circular display
        self.cx_sector = screen_w // 2
        self.cy_sector = screen_h // 2
        self.radius    = screen_h // 2

        # Position (centre coords)
        self.cx = 0.0
        self.cy = 0.0

        # Velocity
        self.vx = 0.0
        self.vy = 0.0

        # Current sprite + rect
        self.image = self.base_image
        self.rect  = self.image.get_rect(center=(self.cx_sector, self.cy_sector))

        # Trial properties
        self.trial_index = 0
        self.label    = "SAFE"   # "THREAT" or "SAFE"
        self.miss_px  = 0.0      # miss distance in pixels

        # Response state
        self.scored_response = None   # None, "THREAT", "SAFE" (only if in outer donut)
        self.raw_response    = None   # first C/N pressed this trial ("THREAT"/"SAFE")
        self.raw_response_time = None # time since spawn (s)
        self.raw_response_phase = None  # "outer" or "inner"

        # Timing state
        self.t_since_spawn  = 0.0    # time since this trial's spawn
        self.t_inner_cross  = None   # time when we first crossed radius/2

        self.reset()

    # ------------------------ helpers ---------------------------------

    def _choose_label_and_miss(self):
        """
        Choose THREAT/SAFE and a miss distance from the appropriate range,
        scaled by GLOBAL_SCALE.
        """
        if random.random() < 0.5:
            self.label = "THREAT"
            lo, hi = self.THREAT_RANGE
        else:
            self.label = "SAFE"
            lo, hi = self.SAFE_RANGE

        # Apply global scaling to miss distances
        lo *= GLOBAL_SCALE
        hi *= GLOBAL_SCALE

        self.miss_px = random.uniform(lo, hi)


    def _trial_outcome(self):
        """
        Return one of:
            "HIT", "MISS", "FALSE_ALARM", "CORRECT_REJECT", or "NR".
        Outcome is based only on the *scored* response (outer donut).
        Late-only responses (inner half) → NR, but RT is still logged.
        """
        if self.scored_response is None:
            return "NR"

        if self.scored_response == "THREAT":
            if self.label == "THREAT":
                return "HIT"
            else:
                return "FALSE_ALARM"
        elif self.scored_response == "SAFE":
            if self.label == "THREAT":
                return "MISS"
            else:
                return "CORRECT_REJECT"

        return "NR"

    def _is_past_sector_edge(self):
        """
        True if the bird has passed outside the circle AND is still heading outward.
        """
        dx = self.cx - self.cx_sector
        dy = self.cy - self.cy_sector
        r2 = dx*dx + dy*dy
        radius2 = self.radius*self.radius

        if r2 <= radius2:
            return False  # still inside

        # dot > 0 means moving outward
        dot = dx*self.vx + dy*self.vy
        return dot > 0

    # ------------------------ main API --------------------------------

    def reset(self):
        """
        New trial:
          1) Increment trial index.
          2) Draw label (THREAT or SAFE) and miss distance.
          3) Draw random approach angle and compute spawn + miss point.
          4) Set velocity along that hypotenuse with a randomised speed and
             rotate sprite accordingly.
        """
        self.trial_index += 1
        self._choose_label_and_miss()

        # Reset timing and response state
        self.t_since_spawn = 0.0
        self.t_inner_cross = None

        self.scored_response = None
        self.raw_response = None
        self.raw_response_time = None
        self.raw_response_phase = None

        # 2) Approach angle (radial line)
        theta = random.uniform(0.0, 2.0 * math.pi)

        # Unit vectors
        u_rad_x = math.cos(theta)
        u_rad_y = math.sin(theta)

        # Spawn on circle edge (centre + radius * radial unit)
        self.cx = self.cx_sector + self.radius * u_rad_x
        self.cy = self.cy_sector + self.radius * u_rad_y

        # Perpendicular direction, randomly choose side (+90° or -90°)
        if random.random() < 0.5:
            # rotate (u_rad_x, u_rad_y) by +90°
            u_perp_x = -u_rad_y
            u_perp_y =  u_rad_x
        else:
            # rotate by -90°
            u_perp_x =  u_rad_y
            u_perp_y = -u_rad_x

        # 3) Miss point: from centre, outwards along perpendicular, length = miss_px
        miss_x = self.cx_sector + self.miss_px * u_perp_x
        miss_y = self.cy_sector + self.miss_px * u_perp_y

        # 4) Direction from spawn to miss point (hypotenuse)
        dir_x = miss_x - self.cx
        dir_y = miss_y - self.cy
        norm  = math.hypot(dir_x, dir_y)
        if norm == 0:
            # pathological; fall back to straight toward centre
            dir_x = self.cx_sector - self.cx
            dir_y = self.cy_sector - self.cy
            norm = math.hypot(dir_x, dir_y)

        dir_x /= norm
        dir_y /= norm

        # Randomise bird speed per trial (e.g., 50–150% of base)
        speed_factor = random.uniform(0.2, 2.7)
        trial_speed = self.speed_px_s * speed_factor

        self.vx = trial_speed * dir_x
        self.vy = trial_speed * dir_y

        # --- compute travel angle and rotate sprite once -------------
        heading_deg = math.degrees(math.atan2(-dir_y, dir_x))
        self.travel_angle_deg = heading_deg - 90.0

        self.image = pygame.transform.rotate(self.base_image, self.travel_angle_deg)
        self.rect  = self.image.get_rect(center=(int(self.cx), int(self.cy)))

        print(f"[Bird] Reset: trial={self.trial_index}, label={self.label}, "
              f"miss={self.miss_px:.1f}px, "
              f"theta={math.degrees(theta):.1f}°, "
              f"start=({self.cx:.1f}, {self.cy:.1f}), "
              f"heading={self.travel_angle_deg:.1f}°, "
              f"speed={trial_speed:.1f}px/s")

    def register_response(self, resp_type):
        if self.raw_response is not None:
            return None  # ignore additional presses

        if resp_type not in ("THREAT", "SAFE"):
            return None

        # mark raw response
        self.raw_response = resp_type
        self.raw_response_time = self.t_since_spawn

        # check inner radius
        dx = self.cx - self.cx_sector
        dy = self.cy - self.cy_sector
        r2 = dx*dx + dy*dy
        inner = RESPONSE_INNER_FRACTION * self.radius
        inner2 = inner * inner

        if r2 > inner2:
            self.scored_response = resp_type
            self.raw_response_phase = "outer"
        else:
            self.raw_response_phase = "inner"

        # END TRIAL IMMEDIATELY
        info = self._immediate_finish()
        return info


    def _build_trial_record(self, outcome):
        """
        Build a dict with all trial data for CSV logging.
        """
        # RT from appearance
        rt_app = self.raw_response_time

        # RT from inner boundary (if we have both times)
        rt_inner = None
        if (self.t_inner_cross is not None) and (self.raw_response_time is not None):
            rt_inner = self.raw_response_time - self.t_inner_cross

        return {
            "trial": self.trial_index,
            "label": self.label,
            "response": self.raw_response if self.raw_response is not None else "",
            "outcome": outcome,
            "rt_from_appearance": rt_app if rt_app is not None else "",
            "rt_from_inner_boundary": rt_inner if rt_inner is not None else "",
            "response_phase": self.raw_response_phase if self.raw_response_phase is not None else "",
        }

    def update(self, dt):
        """
        Move the bird. If it exits the sector, returns:
            (outcome, trial_record_dict)
        Otherwise returns (None, None).
        """
        # Update trial time
        self.t_since_spawn += dt

        # Track when we first cross the inner boundary
        dx = self.cx - self.cx_sector
        dy = self.cy - self.cy_sector
        r2 = dx*dx + dy*dy
        inner = RESPONSE_INNER_FRACTION * self.radius
        inner2 = inner * inner

        # If crossed inner radius with no raw response → TOO SLOW
        if self.raw_response is None and r2 <= inner2:
            self.raw_response_phase = "inner"
            self.t_inner_cross = self.t_since_spawn

            info = self._immediate_finish()

            feedback = {
                "text": info["fb_text"],      # "TOO SLOW!"
                "color": info["fb_color"],    # yellow
                "x": info["x"],
                "y": info["y"],
                "vx": info["vx"],
                "vy": info["vy"],
            }

            return info["outcome"], info["record"], feedback


        # Move bird
        self.cx += self.vx * dt
        self.cy += self.vy * dt
        self.rect.center = (int(self.cx), int(self.cy))

        if self._is_past_sector_edge():
            outcome = self._trial_outcome()
            record = self._build_trial_record(outcome)
            self.reset()  # start a new trial immediately
            return outcome, record, None

        return None, None, None
      
      
    def _immediate_finish(self):
        outcome = self._trial_outcome()
        record = self._build_trial_record(outcome)
        # Capture feedback info
        fb_text, fb_color = self._feedback_from_outcome(outcome)
        info = {
            "outcome": outcome,
            "record": record,
            "fb_text": fb_text,
            "fb_color": fb_color,
            "x": self.cx,
            "y": self.cy,
            "vx": self.vx,
            "vy": self.vy,
        }
        self.reset()
        return info


    def _feedback_from_outcome(self, outcome):
        """
        Return feedback text + color based on the trial outcome.
        """
        if outcome in ("HIT", "CORRECT_REJECT"):
            return "CORRECT!", (120, 255, 140)   # green

        if outcome in ("MISS", "FALSE_ALARM"):
            return "INCORRECT!", (255, 80, 80)   # red

        if outcome == "NR":
            return "TOO SLOW!", (255, 220, 120)  # yellow

        return "", (255, 255, 255)


    def draw(self, screen):
        screen.blit(self.image, self.rect.topleft)



class Ownship:
    """
    Ownship icon drawn at the centre of the display.
    Can switch between 'happy' and 'worried' faces.
    """
    def __init__(self, happy_surf, worried_surf, screen_w, screen_h, scale_factor=1.0):
        # Optionally scale both images with the same factor
        def scale_img(surf):
            if scale_factor != 1.0:
                w, h = surf.get_size()
                new_size = (int(w * scale_factor), int(h * scale_factor))
                return pygame.transform.smoothscale(surf, new_size)
            return surf

        self.happy_image = scale_img(happy_surf)
        self.worried_image = scale_img(worried_surf) if worried_surf is not None else self.happy_image

        # Start happy by default
        self.image = self.happy_image

        self.rect = self.image.get_rect()

        # Ownship always sits at screen centre
        self.cx = screen_w // 2
        self.cy = screen_h // 2
        self.rect.center = (self.cx, self.cy)

    def set_mood(self, mood):
        """
        mood: "happy" or "worried"
        """
        if mood == "worried":
            self.image = self.worried_image
        else:
            # default to happy
            self.image = self.happy_image

        # keep rect centered after any change
        self.rect = self.image.get_rect(center=(self.cx, self.cy))

    def draw(self, screen):
        screen.blit(self.image, self.rect.topleft)



  
# ---------------------------- CLI parsing --------------------------------
  
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ownship-csv",
        type=str,
        required=False,
        default=None,
        help="Path to CSV file with ownship data (optional)"
    )
    return parser.parse_args()



# ------------------------------ Main loop --------------------------------
  
def main():
    args = parse_args()
    
    # Counters for response classifications
    hits = 0
    misses = 0
    false_alarms = 0
    correct_rejects = 0
    nr_misses = 0    # non-responses (no valid C/N before inner radius)
    
    # RT storage (seconds from appearance for first C/N)
    all_rts = []
    
    feedback_list = []
  
    # ---------------------- Ownship / intruder setup ----------------------
    if args.ownship_csv is not None and os.path.exists(args.ownship_csv):
        # Load from CSV as usual
        ownship, intruder, w_csv, h_csv = load_ownship_from_csv(args.ownship_csv)
        print(f"[Init] Loaded ownship from {args.ownship_csv}")
    else:
        # Fallback defaults: no CSV
        print("[Init] No ownship CSV provided or file not found; using defaults.")
        w_csv = SCREEN_WIDTH
        h_csv = SCREEN_HEIGHT

        ownship = {
            "x_px": w_csv / 2.0,
            "y_px": h_csv / 2.0,
            "speed_kn": 200.0,    # default speed
            "bearing_deg": 0.0,   # 0° = North
        }

        intruder = None

  
    pygame.init()
    pygame.display.set_caption("Swoop")
  
    screen = pygame.display.set_mode((int(w_csv), int(h_csv)))
    clock = pygame.time.Clock()
  
    # Font: use bundled Roboto if present, else a system default
    script_dir = os.path.dirname(os.path.abspath(__file__))
    font_path  = os.path.join(script_dir, "fonts", "Roboto-Light.ttf")
        
    # Main font
    if os.path.exists(font_path):
        font = pygame.font.Font(font_path, 24)
        font_small = pygame.font.Font(font_path, 16)
    else:
        font = pygame.font.SysFont("Arial", 24)
        font_small = pygame.font.SysFont("Arial", 16)

    
    # ---------------------- Trial logging setup ----------------------
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results_path = os.path.join(RESULTS_DIR, RESULTS_CSV)

    # Define fieldnames explicitly for stable column order
    fieldnames = [
        "trial",
        "label",
        "response",
        "outcome",
        "rt_from_appearance",
        "rt_from_inner_boundary",
        "response_phase",
    ]
    results_file = open(results_path, "w", newline="")
    results_writer = csv.DictWriter(results_file, fieldnames=fieldnames)
    results_writer.writeheader()

        
    # ----------------------- Ownship sprite -----------------------
    happy_path = os.path.join(script_dir, "images", "face_happy2.png")
    worried_path = os.path.join(script_dir, "images", "face_worried3.png")

    scale_factor = 0.1 * GLOBAL_SCALE  # same scaling for both faces

    if os.path.exists(happy_path):
        print(f"[Ownship] Loading HAPPY sprite from {happy_path}")
        happy_raw = pygame.image.load(happy_path).convert_alpha()
    else:
        print(f"[Ownship] WARNING: {happy_path} not found. Using placeholder.")
        happy_raw = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.circle(happy_raw, (0, 255, 0), (20, 20), 18, 2)

    if os.path.exists(worried_path):
        print(f"[Ownship] Loading WORRIED sprite from {worried_path}")
        worried_raw = pygame.image.load(worried_path).convert_alpha()
    else:
        print(f"[Ownship] WARNING: {worried_path} not found. Falling back to happy.")
        worried_raw = happy_raw

    ownship_sprite = Ownship(
        happy_surf=happy_raw,
        worried_surf=worried_raw,
        screen_w=int(w_csv),
        screen_h=int(h_csv),
        scale_factor=scale_factor,
    )


    # -------------------------- Bird sprite ------------------------------
    bird = None
    bird_img_path = os.path.join(script_dir, "images", "bird1.png")

    # Effective sprite scale = base scale * GLOBAL_SCALE
    # BIRD_BASE_SCALE = 0.1
    bird_scale = BIRD_BASE_SCALE * GLOBAL_SCALE

    if os.path.exists(bird_img_path):
        print(f"[Bird] Loading sprite from {bird_img_path}")
        bird_img_raw = pygame.image.load(bird_img_path).convert_alpha()
        
        # Scale with global zoom
        orig_w, orig_h = bird_img_raw.get_size()
        new_size = (int(orig_w * bird_scale), int(orig_h * bird_scale))

        # For pixel art you *might* prefer scale() (nearest neighbour);
        # smoothscale() will soften it a bit.
        bird_img = pygame.transform.smoothscale(bird_img_raw, new_size)
        # bird_img = pygame.transform.scale(bird_img_raw, new_size)  # try this if you want it sharper

        bird = Bird(bird_img, int(w_csv), int(h_csv), speed_px_s=200.0 * GLOBAL_SCALE)


    else:
        print(f"[Bird] WARNING: {bird_img_path} not found. "
              "Using placeholder debug sprite.")
        # Fallback: draw a bright magenta triangle so you *cannot* miss it
        placeholder = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.polygon(
            placeholder,
            (255, 0, 255, 255),
            [(20, 0), (0, 40), (40, 40)]
        )

        # Scale placeholder with same bird_scale
        ph_w, ph_h = placeholder.get_size()
        ph_size = (int(ph_w * bird_scale), int(ph_h * bird_scale))
        placeholder_scaled = pygame.transform.smoothscale(placeholder, ph_size)

        bird = Bird(placeholder_scaled, int(w_csv), int(h_csv), speed_px_s=200.0 * GLOBAL_SCALE)


  
    # ---------- Noise surfaces & specks (inside central circle) ----------
    # GROUND_SURFACE = pygame.Surface((int(w_csv), int(h_csv)), pygame.SRCALPHA)
    WIND_SURFACE   = pygame.Surface((int(w_csv), int(h_csv)), pygame.SRCALPHA)
    WAKE_SURFACE   = pygame.Surface((int(w_csv), int(h_csv)), pygame.SRCALPHA)

    # Pre-generate random specks restricted to the central circle
    cx_init = int(w_csv) // 2
    cy_init = int(h_csv) // 2
    big_radius_init = int(h_csv) // 2
    r2_init = big_radius_init * big_radius_init

    # --------- Background image clipped to the circular sector ----------
    BG_SECTOR_SURFACE = None
    bg_img_path = os.path.join(script_dir, "images", "ground1.png")

    if os.path.exists(bg_img_path):
        print(f"[Background] Loading texture from {bg_img_path}")
        # Load and scale to full window size
        bg_raw = pygame.image.load(bg_img_path).convert()
        bg_scaled = pygame.transform.smoothscale(
            bg_raw, (int(w_csv), int(h_csv))
        )

        # Surface that will hold the sector-only background
        BG_SECTOR_SURFACE = pygame.Surface(
            (int(w_csv), int(h_csv)), pygame.SRCALPHA
        )
        BG_SECTOR_SURFACE.blit(bg_scaled, (0, 0))

        # Circular alpha mask so only the radar circle shows
        mask = pygame.Surface((int(w_csv), int(h_csv)), pygame.SRCALPHA)
        pygame.draw.circle(
            mask,
            (255, 255, 255, 255),  # solid alpha inside the circle
            (cx_init, cy_init),
            big_radius_init,
        )
        BG_SECTOR_SURFACE.blit(
            mask,
            (0, 0),
            special_flags=pygame.BLEND_RGBA_MULT,
        )
    else:
        print(f"[Background] WARNING: {bg_img_path} not found; no texture background.")
    
    
  
    # # Ground layer specks (uniform alpha & size, but scroll)
    # ground_specks = []
    # for _ in range(NUM_GROUND_SPECKS):
    #     while True:
    #         rx = random.uniform(0, w_csv)
    #         ry = random.uniform(0, h_csv)
    #         dx = rx - cx_init
    #         dy = ry - cy_init
    #         if dx*dx + dy*dy <= r2_init:
    #             ground_specks.append({"x": rx, "y": ry})
    #             break
  
    # Wind layer specks (uniform radius & alpha)
    wind_specks = []
    for _ in range(NUM_WIND_SPECKS):
        while True:
            rx = random.uniform(0, w_csv)
            ry = random.uniform(0, h_csv)
            dx = rx - cx_init
            dy = ry - cy_init
            if dx*dx + dy*dy <= r2_init:
                wind_specks.append({"x": rx, "y": ry})
                break
  
  
    # Prevailing wind state
    wind_speed_kn   = WIND_INIT_SPEED_KT
    wind_bearing_deg = WIND_INIT_BEARING_DEG
      
    # Accumulator for discrete wind updates
    wind_update_accum = 0.0
  
    running = True
    while running:
        # ---- Event handling (quit / ESC + discrete key presses) ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # Rotate bearing: LEFT = decrease, RIGHT = increase
                elif event.key == pygame.K_LEFT:
                    if ownship["bearing_deg"] is None:
                        ownship["bearing_deg"] = 0.0
                    ownship["bearing_deg"] = (ownship["bearing_deg"] - OWN_BRG_STEP_DEG) % 360.0

                elif event.key == pygame.K_RIGHT:
                    if ownship["bearing_deg"] is None:
                        ownship["bearing_deg"] = 0.0
                    ownship["bearing_deg"] = (ownship["bearing_deg"] + OWN_BRG_STEP_DEG) % 360.0

                # Speed: UP = faster, DOWN = slower
                elif event.key == pygame.K_UP:
                    if ownship["speed_kn"] is None:
                        ownship["speed_kn"] = 0.0
                    new_spd = ownship["speed_kn"] + OWN_SPD_STEP_KT
                    new_spd = max(OWN_SPD_MIN_KT, min(OWN_SPD_MAX_KT, new_spd))
                    ownship["speed_kn"] = new_spd

                elif event.key == pygame.K_DOWN:
                    if ownship["speed_kn"] is None:
                        ownship["speed_kn"] = 0.0
                    new_spd = ownship["speed_kn"] - OWN_SPD_STEP_KT
                    new_spd = max(OWN_SPD_MIN_KT, min(OWN_SPD_MAX_KT, new_spd))
                    ownship["speed_kn"] = new_spd
                    
                # C = respond "THREAT"
                elif event.key == pygame.K_c:
                    if bird is not None:
                        info = bird.register_response("THREAT")
                        if info:
                            # Floating feedback
                            feedback_list.append(FloatingFeedback(
                                info["fb_text"], info["fb_color"],
                                info["x"], info["y"],
                                info["vx"], info["vy"]
                            ))

                            # Log
                            results_writer.writerow(info["record"])

                            # RT tracking
                            rt_app = info["record"].get("rt_from_appearance", "")
                            if isinstance(rt_app, (int, float)):
                                all_rts.append(rt_app)

                            # Counters
                            outcome = info["outcome"]
                            if outcome == "HIT":
                                hits += 1
                            elif outcome == "MISS":
                                misses += 1
                            elif outcome == "FALSE_ALARM":
                                false_alarms += 1
                            elif outcome == "CORRECT_REJECT":
                                correct_rejects += 1
                            elif outcome == "NR":
                                nr_misses += 1

                            print("[Bird outcome]", outcome,
                                  f"(H={hits}, M={misses}, NR={nr_misses}, "
                                  f"FA={false_alarms}, CR={correct_rejects})")


                # N = respond "SAFE"
                elif event.key == pygame.K_n:
                    if bird is not None:
                        info = bird.register_response("SAFE")
                        if info:
                            feedback_list.append(FloatingFeedback(
                                info["fb_text"], info["fb_color"],
                                info["x"], info["y"],
                                info["vx"], info["vy"]
                            ))

                            results_writer.writerow(info["record"])

                            rt_app = info["record"].get("rt_from_appearance", "")
                            if isinstance(rt_app, (int, float)):
                                all_rts.append(rt_app)

                            outcome = info["outcome"]
                            if outcome == "HIT":
                                hits += 1
                            elif outcome == "MISS":
                                misses += 1
                            elif outcome == "FALSE_ALARM":
                                false_alarms += 1
                            elif outcome == "CORRECT_REJECT":
                                correct_rejects += 1
                            elif outcome == "NR":
                                nr_misses += 1

                            print("[Bird outcome]", outcome,
                                  f"(H={hits}, M={misses}, NR={nr_misses}, "
                                  f"FA={false_alarms}, CR={correct_rejects})")



        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0

        # Update bird motion, log trials, and update counters
        # Update bird motion, log trials, update counters & RT list
        if bird is not None:
            outcome, trial_record, fb = bird.update(dt)
            
            if fb:
                feedback_list.append(FloatingFeedback(
                    fb["text"], fb["color"],
                    fb["x"], fb["y"],
                    fb["vx"], fb["vy"]
                ))

            if outcome is not None:
                # Log to CSV
                if trial_record is not None:
                    results_writer.writerow(trial_record)

                    # Extract numeric RT from appearance if present
                    rt_app = trial_record.get("rt_from_appearance", "")
                    if isinstance(rt_app, (int, float)):
                        all_rts.append(rt_app)

                # Update summary counters
                if outcome == "HIT":
                    hits += 1
                elif outcome == "MISS":
                    misses += 1
                elif outcome == "FALSE_ALARM":
                    false_alarms += 1
                elif outcome == "CORRECT_REJECT":
                    correct_rejects += 1
                elif outcome == "NR":
                    nr_misses += 1

                print("[Bird outcome]", outcome,
                      f"(H={hits}, M={misses}, NR={nr_misses}, "
                      f"FA={false_alarms}, CR={correct_rejects})")




  
        # -------- Continuous controls (keys held down) --------
        keys = pygame.key.get_pressed()

        # Make sure fields aren't None
        if ownship["bearing_deg"] is None:
            ownship["bearing_deg"] = 0.0
        if ownship["speed_kn"] is None:
            ownship["speed_kn"] = 0.0

        # Bearing: LEFT = decrease, RIGHT = increase
        if keys[pygame.K_LEFT]:
            ownship["bearing_deg"] = (ownship["bearing_deg"] -
                                      OWN_BRG_RATE_DEG_PER_SEC * dt) % 360.0
        if keys[pygame.K_RIGHT]:
            ownship["bearing_deg"] = (ownship["bearing_deg"] +
                                      OWN_BRG_RATE_DEG_PER_SEC * dt) % 360.0

        # Speed: UP = faster, DOWN = slower
        if keys[pygame.K_UP]:
            ownship["speed_kn"] += OWN_SPD_RATE_KT_PER_SEC * dt
        if keys[pygame.K_DOWN]:
            ownship["speed_kn"] -= OWN_SPD_RATE_KT_PER_SEC * dt

        # Clamp speed
        if ownship["speed_kn"] < OWN_SPD_MIN_KT:
            ownship["speed_kn"] = OWN_SPD_MIN_KT
        elif ownship["speed_kn"] > OWN_SPD_MAX_KT:
            ownship["speed_kn"] = OWN_SPD_MAX_KT

  
        # --- Update prevailing wind via Lévy-flight (3 Hz) ---------------
        wind_update_accum += dt
        while wind_update_accum >= WIND_UPDATE_INTERVAL:
            step_dt = WIND_UPDATE_INTERVAL
            wind_update_accum -= WIND_UPDATE_INTERVAL

            # Lévy-flight in speed (heavy-tailed, but clamped)
            speed_step = levy_step(
                scale=WIND_SPEED_RW_STD,
                dt=step_dt,
                alpha=1.5,
                max_step=10.0   # max ±10 kt per update; tweak if you want more drama
            )
            wind_speed_kn += speed_step
            wind_speed_kn = max(WIND_SPEED_MIN_KT, min(WIND_SPEED_MAX_KT, wind_speed_kn))

            # Lévy-flight in bearing (can jump more dramatically)
            bearing_step = levy_step(
                scale=WIND_BEARING_RW_STD,
                dt=step_dt,
                alpha=1.3,      # heavier-tailed than speed
                max_step=25.0   # max ±25° per update; tweak as desired
            )
            wind_bearing_deg = (wind_bearing_deg + bearing_step) % 360.0


        # Clear screen
        screen.fill(BG_COLOR)
  
        # --- Dark circular sector (full disk) centred on screen -----------
        w = screen.get_width()
        h = screen.get_height()
        cx = w // 2
        cy = h // 2
        big_radius = h // 2  # diameter equals screen height
        r2 = big_radius * big_radius
  
        pygame.draw.circle(
            screen,
            SECTOR_COLOR,
            (cx, cy),
            big_radius,
            0  # filled
        )
        
        # --- Blit the textured background inside the sector, if available ---
        if BG_SECTOR_SURFACE is not None:
            screen.blit(BG_SECTOR_SURFACE, (0, 0))
        
        # ---------------------- Update intruder (if any) ----------------------
        if intruder is not None:
            # Default missing values
            if intruder.get("speed_kn") is None:
                intruder["speed_kn"] = 0.0
            if intruder.get("bearing_deg") is None:
                intruder["bearing_deg"] = 0.0

            spd_i = intruder["speed_kn"]
            brg_i = intruder["bearing_deg"]

            # Aviation-style: 0° = North, 90° = East
            ang_i = math.radians(brg_i)
            vx_i = math.sin(ang_i) * spd_i * INTRUDER_PX_PER_KT
            vy_i = -math.cos(ang_i) * spd_i * INTRUDER_PX_PER_KT

            intruder["x_px"] += vx_i * dt
            intruder["y_px"] += vy_i * dt

            # Let it wrap if it leaves the screen horizontally/vertically
            if intruder["x_px"] < 0:
                intruder["x_px"] += w
            elif intruder["x_px"] > w:
                intruder["x_px"] -= w

            if intruder["y_px"] < 0:
                intruder["y_px"] += h
            elif intruder["y_px"] > h:
                intruder["y_px"] -= h

  
        # ---------- Compute background velocities --------------------------
        # Ownship vector
        ownship_speed_kn = ownship.get("speed_kn") or 0.0
        ownship_bearing_deg = ownship.get("bearing_deg")
  
        ownship_vx = 0.0
        ownship_vy = 0.0
        if ownship_bearing_deg is not None and ownship_speed_kn is not None:
            # Aviation-style: 0° = North (up), 90° = East (right)
            ang = math.radians(ownship_bearing_deg)
            ownship_vx = math.sin(ang) * ownship_speed_kn * WINDFIELD_PX_PER_KT
            ownship_vy = -math.cos(ang) * ownship_speed_kn * WINDFIELD_PX_PER_KT
  
        # Prevailing wind vector
        wind_ang = math.radians(wind_bearing_deg)
        wind_vx = math.sin(wind_ang) * wind_speed_kn * WINDFIELD_PX_PER_KT
        wind_vy = -math.cos(wind_ang) * wind_speed_kn * WINDFIELD_PX_PER_KT
  
        # Ground layer scrolls opposite to ownship motion only
        ground_vx = -ownship_vx
        ground_vy = -ownship_vy
  
        # Wind layer scrolls opposite to ownship, with the wind
        wind_layer_vx = (-WIND_LAYER_OWNSHIP_WEIGHT * ownship_vx +
                          WIND_LAYER_WIND_WEIGHT * wind_vx)
        wind_layer_vy = (-WIND_LAYER_OWNSHIP_WEIGHT * ownship_vy +
                          WIND_LAYER_WIND_WEIGHT * wind_vy)
  
  
        # # ------------------- Ground layer update/draw ----------------------
        # GROUND_SURFACE.fill((0, 0, 0, 0))
        # 
        # for speck in ground_specks:
        #     speck["x"] += ground_vx * dt
        #     speck["y"] += ground_vy * dt
        # 
        #     dx = speck["x"] - cx
        #     dy = speck["y"] - cy
        # 
        #     # If it leaves the circular sector, respawn inside it
        #     if dx*dx + dy*dy > r2:
        #         while True:
        #             rx = random.uniform(cx - big_radius, cx + big_radius)
        #             ry = random.uniform(cy - big_radius, cy + big_radius)
        #             dx2 = rx - cx
        #             dy2 = ry - cy
        #             if dx2*dx2 + dy2*dy2 <= r2:
        #                 speck["x"] = rx
        #                 speck["y"] = ry
        #                 dx = dx2
        #                 dy = dy2
        #                 break
        # 
        #     ix = int(speck["x"])
        #     iy = int(speck["y"])
        # 
        #     if 0 <= ix < w and 0 <= iy < h:
        #         # Radial factor: brighter in the centre, darker near the edge
        #         r_norm = math.sqrt(dx*dx + dy*dy) / float(big_radius)
        #         if r_norm > 1.0:
        #             r_norm = 1.0
        # 
        #         # Interpolate between highlight (centre) and shadow (edge)
        #         t = r_norm
        #         base_r = (1.0 - t) * GROUND_HIGHLIGHT[0] + t * GROUND_SHADOW[0]
        #         base_g = (1.0 - t) * GROUND_HIGHLIGHT[1] + t * GROUND_SHADOW[1]
        #         base_b = (1.0 - t) * GROUND_HIGHLIGHT[2] + t * GROUND_SHADOW[2]
        # 
        #         # Mix in the mid desert tone slightly for cohesion
        #         base_r = 0.7 * base_r + 0.3 * GROUND_COLOR[0]
        #         base_g = 0.7 * base_g + 0.3 * GROUND_COLOR[1]
        #         base_b = 0.7 * base_b + 0.3 * GROUND_COLOR[2]
        # 
        #         # Small jitter for mottled sand
        #         jitter = random.randint(-8, 8)
        #         r_col = max(0, min(255, int(base_r) + jitter))
        #         g_col = max(0, min(255, int(base_g) + jitter))
        #         b_col = max(0, min(255, int(base_b) + jitter))
        # 
        #         # Slightly fade out towards the edge, then jitter
        #         base_alpha = GROUND_ALPHA * (1.0 - 0.5 * r_norm)
        #         alpha = jitter_alpha(base_alpha)
        # 
        # 
        #         # Vary speck size a bit (mostly 1px, occasional 2px grains)
        #         radius = 1 if random.random() < 0.85 else 2
        # 
        #         pygame.draw.circle(
        #             GROUND_SURFACE,
        #             (r_col, g_col, b_col, alpha),
        #             (ix, iy),
        #             radius
        #         )

  
        # -------------------- Wind layer update/draw -----------------------
        WIND_SURFACE.fill((0, 0, 0, 0))
  
        for speck in wind_specks:
            speck["x"] += wind_layer_vx * dt
            speck["y"] += wind_layer_vy * dt
  
            dx = speck["x"] - cx
            dy = speck["y"] - cy
  
            # If it leaves the circular sector, respawn inside it
            if dx*dx + dy*dy > r2:
                while True:
                    rx = random.uniform(cx - big_radius, cx + big_radius)
                    ry = random.uniform(cy - big_radius, cy + big_radius)
                    dx2 = rx - cx
                    dy2 = ry - cy
                    if dx2*dx2 + dy2*dy2 <= r2:
                        speck["x"] = rx
                        speck["y"] = ry
                        dx = dx2
                        dy = dy2
                        break
  
  
            ix = int(speck["x"])
            iy = int(speck["y"])

            ix = int(speck["x"])
            iy = int(speck["y"])

            if 0 <= ix < w and 0 <= iy < h:
                # Interpolate between pollen dark/light colours
                t = random.random()
                base_r = (1.0 - t) * WIND_COLOR_DARK[0] + t * WIND_COLOR_LIGHT[0]
                base_g = (1.0 - t) * WIND_COLOR_DARK[1] + t * WIND_COLOR_LIGHT[1]
                base_b = (1.0 - t) * WIND_COLOR_DARK[2] + t * WIND_COLOR_LIGHT[2]

                # Small jitter to avoid perfectly flat colour
                jitter = random.randint(-8, 8)
                r_col = max(0, min(255, int(base_r) + jitter))
                g_col = max(0, min(255, int(base_g) + jitter))
                b_col = max(0, min(255, int(base_b) + jitter))

                # Random alpha per speck
                alpha_min = 60
                alpha_max = WIND_ALPHA  # upper bound from global
                alpha = random.randint(alpha_min, alpha_max)

                # Random radius in [0.5, 3] scaled by GLOBAL_SCALE
                radius_f = random.uniform(0.5, 3.0) * GLOBAL_SCALE
                radius = max(1, int(round(radius_f)))

                pygame.draw.circle(
                    WIND_SURFACE,
                    (r_col, g_col, b_col, alpha),
                    (ix, iy),
                    radius,
                )



        # Blit both layers on top of the sector (inside circle only)
        # screen.blit(GROUND_SURFACE, (0, 0))
        screen.blit(WIND_SURFACE, (0, 0))


        # ---------------------- Inner cutoff ring(s) -------------------------
        inner_r = int(big_radius * RESPONSE_INNER_FRACTION)

        # 1) Hollow red inner ring at RESPONSE_INNER_FRACTION
        inner_surf = pygame.Surface((inner_r * 2, inner_r * 2), pygame.SRCALPHA)

        RING_WIDTH = 3  # tweak thickness as you like

        pygame.draw.circle(
            inner_surf,
            INNER_RADIUS_COLOR,
            (inner_r, inner_r),  # center in the temp surface
            inner_r,
            width=RING_WIDTH     # >0 = outline only
        )

        screen.blit(inner_surf, (cx - inner_r, cy - inner_r))

        # 2) Filled disc at 50 px miss distance (THREAT/SAFE boundary)
        # SEP_RADIUS_PX is already scaled by GLOBAL_SCALE
        # subtle, semi-transparent fill; reuse same red hue but lighter alpha
        SEPARATION_DISC_COLOR = (255, 80, 80, 80)

        sep_surf = pygame.Surface((SEP_RADIUS_PX * 2, SEP_RADIUS_PX * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            sep_surf,
            SEPARATION_DISC_COLOR,
            (SEP_RADIUS_PX, SEP_RADIUS_PX),
            SEP_RADIUS_PX,
            width=0  # filled disc
        )

        screen.blit(sep_surf, (cx - SEP_RADIUS_PX, cy - SEP_RADIUS_PX))




        # ----------------------- Wind compass HUD --------------------------
        # Compass center on right side of screen
        compass_cx = w - COMPASS_RADIUS - COMPASS_MARGIN_X
        compass_cy = h // 2
  
        # Background circle
        pygame.draw.circle(
            screen,
            COMPASS_BG_COLOR,
            (compass_cx, compass_cy),
            COMPASS_RADIUS,
            0
        )
  
        # Outer ring
        pygame.draw.circle(
            screen,
            COMPASS_RING_COLOR,
            (compass_cx, compass_cy),
            COMPASS_RADIUS,
            2
        )
  
        # Wind direction line (0° = up, 90° = right)
        wind_ang = math.radians(wind_bearing_deg)
        dx = math.sin(wind_ang) * (COMPASS_RADIUS - 8)
        dy = -math.cos(wind_ang) * (COMPASS_RADIUS - 8)
  
        pygame.draw.line(
            screen,
            COMPASS_LINE_COLOR,
            (compass_cx, compass_cy),
            (compass_cx + int(dx), compass_cy + int(dy)),
            3
        )
  
        # Labels: bearing at top, speed at bottom
        bearing_label = f"{wind_bearing_deg:03.0f}°"
        speed_label   = f"{wind_speed_kn:4.1f} kt"
  
        # Top (bearing)
        bearing_surf = font.render(bearing_label, True, TEXT_COLOR)
        bearing_rect = bearing_surf.get_rect(
            center=(compass_cx, compass_cy - COMPASS_RADIUS - 20)
        )
        screen.blit(bearing_surf, bearing_rect)
  
        # Bottom (speed)
        speed_surf = font.render(speed_label, True, TEXT_COLOR)
        speed_rect = speed_surf.get_rect(
            center=(compass_cx, compass_cy + COMPASS_RADIUS + 20)
        )
        screen.blit(speed_surf, speed_rect)
  
        # ----------------------- Draw ownship circle -----------------------
        x = int(ownship["x_px"])
        y = int(ownship["y_px"])
        pygame.draw.circle(screen, CIRCLE_COLOR, (x, y), CIRCLE_RADIUS, 1)
        
        # ----------------------- Draw intruder (if any) -----------------------
        if intruder is not None:
            ix = int(intruder["x_px"])
            iy = int(intruder["y_px"])

            # Main intruder dot
            pygame.draw.circle(
                screen,
                INTRUDER_COLOR,
                (ix, iy),
                INTRUDER_RADIUS,
                0
            )

            # Small heading "nose" to show direction of travel
            if intruder.get("bearing_deg") is not None:
                ang_i = math.radians(intruder["bearing_deg"])
                nose_dx = math.sin(ang_i) * INTRUDER_HEADING_LEN
                nose_dy = -math.cos(ang_i) * INTRUDER_HEADING_LEN

                pygame.draw.line(
                    screen,
                    INTRUDER_COLOR,
                    (ix, iy),
                    (int(ix + nose_dx), int(iy + nose_dy)),
                    2,
                )

          
        # ------------------- Thrust, drag & components --------------------
        if ownship["speed_kn"] is not None and ownship["bearing_deg"] is not None:
            spd = ownship["speed_kn"]
            brg_deg = ownship["bearing_deg"]

            # Aviation-style bearing: 0° = North (up), 90° = East (right)
            ang = math.radians(brg_deg)

            # Unit direction of travel in *screen* coords
            # (ux, uy) scaled by speed → velocity in "knots" space
            ux = math.sin(ang)      # +x = East
            uy = -math.cos(ang)     # +y = South on screen, North is negative

            # Common scale: total vector length is strictly proportional to speed
            scale = spd * THRUST_VECTOR_PX_PER_KT

            # ---------- Thrust vector (forward, along direction of travel) ----
            thrust_dx = ux * scale
            thrust_dy = uy * scale

            pygame.draw.line(
                screen,
                THRUST_VECTOR_COLOR,
                (x, y),
                (int(x + thrust_dx), int(y + thrust_dy)),
                VECTOR_LINE_WIDTH,
            )

            # ---------- Drag vector (rearward, opposite direction) ------------
            drag_dx = -ux * scale
            drag_dy = -uy * scale

            pygame.draw.line(
                screen,
                DRAG_VECTOR_COLOR,
                (x, y),
                (int(x + drag_dx), int(y + drag_dy)),
                VECTOR_LINE_WIDTH,
            )

            # ---------- Velocity components: E–W and N–S ----------------------
            # Horizontal component: purely east–west (x only)
            comp_ew_dx = ux * scale
            comp_ew_dy = 0.0

            pygame.draw.line(
                screen,
                COMP_EW_COLOR,
                (x, y),
                (int(x + comp_ew_dx), int(y + comp_ew_dy)),
                COMP_VECTOR_LINE_WIDTH,
            )

            # Vertical component: purely north–south (y only)
            # (Remember: +y = south on screen, so "north" is negative.)
            comp_ns_dx = 0.0
            comp_ns_dy = uy * scale

            pygame.draw.line(
                screen,
                COMP_NS_COLOR,
                (x, y),
                (int(x + comp_ns_dx), int(y + comp_ns_dy)),
                COMP_VECTOR_LINE_WIDTH,
            )


        # ----------------------- Outcome bar chart & RT hist -----------------------
        # Layout: 10 px from left; bar centered in upper half, hist in lower half
        panel_x = 10
        panel_w = 260
        panel_h = 130

        mid_y = h // 2

        # Bar chart: centered in upper half
        bar_center_y = mid_y // 2
        bar_y = bar_center_y - panel_h // 2

        # Histogram: centered in lower half
        hist_center_y = (mid_y + h) // 2
        hist_y = hist_center_y - panel_h // 2

        bar_rect = (panel_x, bar_y, panel_w, panel_h)
        hist_rect = (panel_x, hist_y, panel_w, panel_h)

        # Accuracy and mean RT summary (centre left, between bar & hist)
        total_scored = hits + misses + false_alarms + correct_rejects
        correct = hits + correct_rejects

        if total_scored > 0:
            acc = correct / total_scored
            acc_pct = acc * 100.0
            acc_str = f"ACC {acc_pct:5.1f}%"
        else:
            acc_str = "ACC --- %"

        if all_rts:
            mean_rt = sum(all_rts) / len(all_rts)
            mrt_str = f"MEAN RT {mean_rt:.3f} s"
        else:
            mrt_str = "MEAN RT ---"

        # Render on two lines
        acc_surf = font.render(acc_str, True, TEXT_COLOR)
        mrt_surf = font.render(mrt_str, True, TEXT_COLOR)

        # Vertical gap between bar chart and histogram
        gap_top = bar_y + panel_h
        gap_bottom = hist_y

        total_text_h = acc_surf.get_height() + mrt_surf.get_height() + 4  # 4 px spacing
        stats_y_start = gap_top + (gap_bottom - gap_top - total_text_h) / 2

        stats_x = panel_x  # left side

        # First line: ACC
        screen.blit(acc_surf, (stats_x, stats_y_start))
        # Second line: MEAN RT
        screen.blit(mrt_surf, (stats_x, stats_y_start + acc_surf.get_height() + 4))


        # Now draw bar chart and histogram
        outcome_counts = {
            "HIT": hits,
            "MISS": misses,
            "NR": nr_misses,
            "FA": false_alarms,
            "CR": correct_rejects,
        }
        # Pass overall accuracy (acc) as proportion correct for red line
        prop_correct = acc if total_scored > 0 else None
        draw_bar_chart(screen, font_small, bar_rect, outcome_counts, prop_correct=prop_correct)

        draw_rt_histogram(screen, font_small, hist_rect, all_rts)


        # SPD/BRG label at top of screen
        label_parts = []
        if ownship["speed_kn"] is not None:
            label_parts.append(f"SPD {ownship['speed_kn']:.0f} kt")
        if ownship["bearing_deg"] is not None:
            label_parts.append(f"BRG {ownship['bearing_deg']:.0f}°")
  
        if label_parts:
            label = "   ".join(label_parts)
            draw_text(
                screen,
                font,
                label,
                TEXT_COLOR,
                (w // 2, 30),
            )
            
        # Update & draw floating feedback
        to_remove = []
        for fb in feedback_list:
            if fb.update(dt):
                to_remove.append(fb)
            fb.draw(screen, font)

        for fb in to_remove:
            feedback_list.remove(fb)

        
        score_label = (f"HIT {hits}   MISS {misses}   "
                       f"FA {false_alarms}   CR {correct_rejects}   NR {nr_misses}")
        draw_text(
            screen,
            font,
            score_label,
            TEXT_COLOR,
            (w // 2, h - 30),  # bottom centre
        )


        # Intruder HUD (optional)
        if intruder is not None:
            intr_parts = []
            if intruder.get("speed_kn") is not None:
                intr_parts.append(f"INTR SPD {intruder['speed_kn']:.0f} kt")
            if intruder.get("bearing_deg") is not None:
                intr_parts.append(f"INTR BRG {intruder['bearing_deg']:.0f}°")

            if intr_parts:
                intr_label = "   ".join(intr_parts)
                draw_text(
                    screen,
                    font,
                    intr_label,
                    TEXT_COLOR,
                    (w // 2, 60),  # slightly below ownship label
                )
                
        # ------------------- Update ownship mood by accuracy -------------
        # Only scored outcomes (no NR): HIT, MISS, FA, CR
        total_scored = hits + misses + false_alarms + correct_rejects
        correct = hits + correct_rejects

        if total_scored > 0:
            accuracy = correct / total_scored
            if accuracy < 0.55:
                ownship_sprite.set_mood("worried")
            else:
                ownship_sprite.set_mood("happy")
        else:
            # No trials yet → start happy
            ownship_sprite.set_mood("happy")

        ownship_sprite.draw(screen)

        # Draw bird on top of other elements
        if bird is not None:
            bird.draw(screen)

        pygame.display.flip()

    running = False  # after loop exits
    results_file.close()
    pygame.quit()

  
  
if __name__ == "__main__":
    main()
