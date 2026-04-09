# swoop.py
import atexit
import csv
import os
import argparse
import math
import random 
import time
import pygame

# -------------------------- Output logging -------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "output")
RESULTS_CSV = "results_swoop_precision_rt.csv"

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

NUM_WIND_SPECKS     = 2400             # density
  
# Wind layer visual properties (uniform)
WIND_RADIUS         = max(1, int(round(3 * GLOBAL_SCALE)))
# Soft summery pollen palette (warm yellow/white)
WIND_COLOR_DARK     = (220, 200, 70)   # deeper pollen yellow
WIND_COLOR_LIGHT    = (255, 250, 220)  # pale creamy pollen/white

WIND_ALPHA = 140               # slightly more visible (optional)
  
# How fast the wind field scrolls per knot of speed (pixels/sec/knot)
WINDFIELD_PX_PER_KT = 2.0 * GLOBAL_SCALE
  
# ---------------------- Prevailing wind random walk ----------------------
  
WIND_INIT_SPEED_KT    = 100.0   # initial prevailing wind speed
WIND_INIT_BEARING_DEG = 180.0   # initial prevailing wind bearing (0=N, 90=E)
  
WIND_SPEED_MIN_KT    = 100.0
WIND_SPEED_MAX_KT    = 500.0
  
# Random-walk strengths (per second, used as Lévy scales)
WIND_SPEED_RW_STD    = 2.0      # ~typical speed step size (knots)
WIND_BEARING_RW_STD  = 2.0      # ~typical bearing step size (degrees)
  
# How often to update wind (seconds)
WIND_UPDATE_INTERVAL = 1.0 / 3.0   # 3 times per second
  
# How much each component contributes to wind-layer scrolling
WIND_LAYER_OWNSHIP_WEIGHT = 0.5
WIND_LAYER_WIND_WEIGHT    = 1 - WIND_LAYER_OWNSHIP_WEIGHT
  
# ----------------------------- Compass HUD --------------------------------
  
COMPASS_RADIUS     = int(100 * GLOBAL_SCALE)
COMPASS_MARGIN_X   = 40   # distance from right edge
COMPASS_LINE_COLOR = (240, 240, 240)  # same as TEXT_COLOR
COMPASS_BG_COLOR   = (0, 0, 0)        # black circle background
COMPASS_RING_COLOR = (80, 80, 80)     # outer ring


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

def draw_bar_chart(screen, font_axis, font_labels, rect, counts, prop_correct=None):
    """
    Draw a simple bar chart of outcome proportions in the given rect.

    counts: dict with keys like
        "HIT", "MISS", "NR", "FA", "CR",
        "PM HIT", "PM MISS", "PM NR", "PM FA"

    Y-axis is fixed from 0 to 1.

    prop_correct: optional float in [0,1] giving overall proportion correct
    (for the red reference line). If None, no reference line is drawn.
    """
    x, y, w, h = rect
    total = sum(counts.values())
    if total <= 0:
        # No data yet at all
        label = font_axis.render("No data", True, TEXT_COLOR)
        screen.blit(label, (x + 5, y + 5))
        return

    # Background
    pygame.draw.rect(screen, (10, 10, 10), rect, 0)
    pygame.draw.rect(screen, (80, 80, 80), rect, 1)

    # Outcome order & colours
    base_keys = ["HIT", "MISS", "NR", "FA", "CR",
                 "PM HIT", "PM MISS", "PM NR", "PM FA"]
    keys = [k for k in base_keys if k in counts]

    # If no recognised keys: bail out gracefully
    if not keys:
        label = font_axis.render("No data", True, TEXT_COLOR)
        screen.blit(label, (x + 5, y + 5))
        return

    colors = {
        # Normal bird outcomes
        "HIT":  (120, 255, 140),   # green-ish
        "MISS":  (255, 120, 120),   # red-ish
        "NR": (255, 200, 120),   # amber
        "FA": (255, 160, 220),   # pink-ish
        "CR": (150, 200, 255),   # blue-ish

        # GULL / PM-coded outcomes
        "PM HIT":  (80,  240, 160),  # slightly different green
        "PM MISS":  (255, 80,  80),   # red for missed gull
        "PM NR": (255, 220, 120),  # amber NR for gull
        "PM FA": (200, 140, 255),  # purple-ish for gull false alarms
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
    label1 = font_axis.render("1.0", True, TEXT_COLOR)
    label0 = font_axis.render("0.0", True, TEXT_COLOR)
    screen.blit(
        label1,
        (axis_x + 4, axis_top - label1.get_height() // 2),
    )
    screen.blit(
        label0,
        (axis_x + 4, axis_bottom - label0.get_height() // 2),
    )

    # Y-axis label "p" above axis
    ylabel = font_axis.render("p", True, TEXT_COLOR)
    screen.blit(
        ylabel,
        (axis_x, y - ylabel.get_height() + 5),
    )

    # ---- Bars (scaled 0–1 to axis height) ----------------------------
    bar_margin = 4
    n = len(keys)
    bar_area_x0 = axis_x + 30
    bar_area_width = w - (bar_area_x0 - x) - bar_margin
    if bar_area_width < 10:
        bar_area_width = max(10, w - 2 * bar_margin)

    bar_width = (bar_area_width - (n + 1) * bar_margin) / n
    max_height = axis_bottom - axis_top  # corresponds to proportion = 1

    total_counts = sum(counts.values())

    # Draw bars
    for i, k in enumerate(keys):
        count = counts.get(k, 0)
        prop = count / total_counts if total_counts > 0 else 0.0
        bh = prop * max_height

        bx = bar_area_x0 + bar_margin + i * (bar_width + bar_margin)
        by = axis_bottom - bh

        pygame.draw.rect(
            screen,
            colors.get(k, (200, 200, 200)),
            (bx, by, bar_width, bh),
        )

        # Category label under bar (tiny font)
        label = font_labels.render(k, True, TEXT_COLOR)
        lr = label.get_rect(center=(bx + bar_width / 2, y + h - 8))
        screen.blit(label, lr)

    # ---- Horizontal line at overall accuracy (if given) --------------
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

    - On each trial, this object can behave as:
        * a normal THREAT/SAFE bird  (respond with C/N),
        * a SEAGULL oddball          (respond with key '9').

    - Bird image is rotated so its 'top' faces the direction of travel.
    """

    THREAT_RANGE = (0.0, 45.0)   # base pixels
    SAFE_RANGE   = (55.0, 100.0) # base pixels
    P_SEAGULL    = 0.10          # 10% GULL trials

    def __init__(
        self,
        bird_image_surf,
        gull_image_surf,
        screen_w,
        screen_h,
        speed_px_s=200.0,
        use_precision_timing=False,
    ):
        # Base sprite for normal THREAT/SAFE trials
        self.base_image = bird_image_surf

        # Seagull sprite for SEAGULL trials; if None, fall back to base
        if gull_image_surf is not None:
            self.seagull_image = gull_image_surf
        else:
            self.seagull_image = bird_image_surf

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
        self.use_precision_timing = use_precision_timing

        # Trial properties
        self.trial_index = 0
        self.label    = "SAFE"   # "THREAT", "SAFE", or "SEAGULL"
        self.miss_px  = 0.0      # miss distance in pixels

        # Species flag for this trial
        self.is_seagull = False  # False = normal THREAT/SAFE bird

        # Response state
        self.scored_response = None   # None, "THREAT", "SAFE", "SEAGULL"
        self.raw_response    = None   # first C/N/9 pressed this trial
        self.raw_response_time = None # time since spawn (s)
        self.raw_response_phase = None  # "outer" or "inner"

        # Timing state
        self.spawn_time = None
        self.t_since_spawn  = 0.0    # time since this trial's spawn
        self.t_inner_cross  = None   # time when we first crossed radius/2

        self.reset()


    # ------------------------ helpers ---------------------------------

    def _choose_label_and_miss(self):
        """
        Choose THREAT/SAFE and a miss distance from the appropriate range,
        scaled by GLOBAL_SCALE. Used only for normal (non-seagull) trials.
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

    def _choose_seagull_miss(self):
        """
        Miss distance range for seagull trials.
        For now we just reuse the SAFE_RANGE band, scaled.
        """
        lo, hi = self.SAFE_RANGE
        lo *= GLOBAL_SCALE
        hi *= GLOBAL_SCALE
        self.miss_px = random.uniform(lo, hi)

    def _trial_outcome(self):
        """
        Return one of:
            "HIT", "MISS", "FALSE_ALARM", "CORRECT_REJECT", "NR",
            "GULL_HIT", "GULL_MISS", or "GULL_FALSE_ALARM".

        Outcome is based only on the *scored* response (outer donut).
        Late-only responses (inner half) → NR, but RT is still logged.
        """
        if self.scored_response is None:
            return "NR"

        # -------- Seagull trials --------------------------------------
        if self.is_seagull:
            if self.scored_response == "SEAGULL":
                return "GULL_HIT"
            elif self.scored_response in ("THREAT", "SAFE"):
                return "GULL_MISS"
            else:
                return "NR"

        # -------- Normal THREAT/SAFE bird trials ----------------------
        # Oddball key '9' on a *non*-seagull trial → PM false alarm
        if self.scored_response == "SEAGULL":
            return "GULL_FALSE_ALARM"

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

    def _start_trial_timer(self):
        self.spawn_time = time.perf_counter() if self.use_precision_timing else None
        self.t_since_spawn = 0.0
        self.t_inner_cross = None

    def _elapsed_since_spawn(self, dt):
        if self.use_precision_timing:
            if self.spawn_time is None:
                self.spawn_time = time.perf_counter()
                return 0.0
            return time.perf_counter() - self.spawn_time

        return self.t_since_spawn + dt

    # ------------------------ main API --------------------------------

    def reset(self):
        """
        New trial:
          1) Increment trial index.
          2) Decide whether this trial is a normal bird or a seagull.
          3) Draw label/miss distance.
          4) Draw random approach angle and compute spawn + miss point.
          5) Set velocity along that hypotenuse with a randomised speed and
             rotate sprite accordingly.
        """
        self.trial_index += 1

        # ----- Decide species for this trial ---------------------------
        if random.random() < self.P_SEAGULL:
            self.is_seagull = True
            self.label = "SEAGULL"
            self._choose_seagull_miss()
        else:
            self.is_seagull = False
            self._choose_label_and_miss()

        # Reset timing and response state
        self._start_trial_timer()

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

        base = self.seagull_image if self.is_seagull else self.base_image
        self.image = pygame.transform.rotate(base, self.travel_angle_deg)
        self.rect  = self.image.get_rect(center=(int(self.cx), int(self.cy)))

        print(
            f"[Bird] Reset: trial={self.trial_index}, "
            f"species={'SEAGULL' if self.is_seagull else 'BIRD'}, "
            f"label={self.label}, miss={self.miss_px:.1f}px, "
            f"theta={math.degrees(theta):.1f}°, "
            f"start=({self.cx:.1f}, {self.cy:.1f}), "
            f"heading={self.travel_angle_deg:.1f}°, "
            f"speed={trial_speed:.1f}px/s"
        )

    def register_response(self, resp_type):
        """
        resp_type: "THREAT", "SAFE", or "SEAGULL" (from keys C, N, 9).
        Returns trial info dict (or None if response ignored).
        """
        if self.raw_response is not None:
            return None  # ignore additional presses

        if resp_type not in ("THREAT", "SAFE", "SEAGULL"):
            return None

        # mark raw response
        self.raw_response = resp_type
        self.raw_response_time = self._elapsed_since_spawn(0.0)

        # check inner radius
        dx = self.cx - self.cx_sector
        dy = self.cy - self.cy_sector
        r2 = dx*dx + dy*dy
        inner = RESPONSE_INNER_FRACTION * self.radius
        inner2 = inner * inner

        if r2 > inner2:
            # scored (outer donut) response
            self.scored_response = resp_type
            self.raw_response_phase = "outer"
        else:
            # inner-only (too late) response
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
            (outcome, trial_record_dict, feedback_dict_or_None)
        Otherwise returns (None, None, None).
        """
        # Update trial time
        self.t_since_spawn = self._elapsed_since_spawn(dt)

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

        # Seagull-specific feedback
        if outcome == "GULL_HIT":
            return "GULL!", (120, 255, 140)      # green-ish
        if outcome == "GULL_MISS":
            return "MISSED GULL!", (255, 80, 80) # red-ish
        if outcome == "GULL_FALSE_ALARM":
            return "NO GULL!", (255, 80, 80)     # red-ish

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
  
def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-csv",
        type=str,
        default=RESULTS_CSV,
        help="Output CSV filename written under the output directory",
    )
    parser.add_argument(
        "--precision-rt",
        action="store_true",
        help="Use high-resolution monotonic timing for reaction times",
    )
    parser.add_argument(
        "--max-trials",
        type=int,
        default=None,
        help="Stop automatically after the given number of completed trials",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use SDL dummy drivers so the task can be smoke-tested without a display",
    )
    return parser.parse_args(argv)



# ------------------------------ Main loop --------------------------------
  
def main(argv=None, default_results_csv=RESULTS_CSV, default_precision_timing=True):
    args = parse_args(argv)
    if args.results_csv == RESULTS_CSV and default_results_csv != RESULTS_CSV:
        args.results_csv = default_results_csv
    if default_precision_timing:
        args.precision_rt = True
    if args.max_trials is not None and args.max_trials < 1:
        raise ValueError("--max-trials must be a positive integer")
    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    
    # Counters for response classifications
    hits = 0              # stim = "THREAT" and keypress = "C"
    misses = 0           # stim = "THREAT" and keypress = "N"
    false_alarms = 0     # stim = "SAFE" and keypress = "C"
    correct_rejects = 0  # stim = "SAFE" and keypress = "N"

    # Non-responses (no valid C/N/9 before inner radius)
    # Split into THREAT/SAFE vs GULL NR
    nr_misses = 0        # THREAT/SAFE trials with NR
    pm_nr_misses = 0     # GULL trials with NR

    # PM / GULL counters
    pm_hits = 0          # stim = "GULL" and keypress = "9" in time
    pm_misses = 0        # stim = "GULL" and wrong C/N response (in time)
    pm_false_alarms = 0  # stim != "GULL" and keypress = "9"

    
    # RT storage (seconds from appearance for first C/N)
    all_rts = []
    gull_rts = []   # RTs for GULL_HIT trials only
    
    # Feedback storage
    feedback_list = []
  
    # ---------------------- Display setup ----------------------
    w_csv = SCREEN_WIDTH
    h_csv = SCREEN_HEIGHT
    ownship = {
        "x_px": w_csv / 2.0,
        "y_px": h_csv / 2.0,
    }

  
    pygame.init()
    pygame.display.set_caption("Swoop")
  
    screen = pygame.display.set_mode((int(w_csv), int(h_csv)))
    clock = pygame.time.Clock()
  
    # Font: use bundled Roboto if present, else a system default
    font_path  = os.path.join(SCRIPT_DIR, "fonts", "Roboto-Light.ttf")
        
    # Main font
    if os.path.exists(font_path):
        font       = pygame.font.Font(font_path, 24)
        font_small = pygame.font.Font(font_path, 16)
        font_tiny  = pygame.font.Font(font_path, 10)
    else:
        font       = pygame.font.SysFont("Arial", 24)
        font_small = pygame.font.SysFont("Arial", 16)
        font_tiny  = pygame.font.SysFont("Arial", 10)

    
    # ---------------------- Trial logging setup ----------------------
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results_path = os.path.join(RESULTS_DIR, args.results_csv)

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
    results_file = open(results_path, "w", newline="", buffering=1)
    atexit.register(results_file.close)
    atexit.register(pygame.quit)
    results_writer = csv.DictWriter(results_file, fieldnames=fieldnames)
    results_writer.writeheader()

        
    # ----------------------- Ownship sprite -----------------------
    happy_path = os.path.join(SCRIPT_DIR, "images", "face_happy2.png")
    worried_path = os.path.join(SCRIPT_DIR, "images", "face_worried2.png")

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
    bird_img_path = os.path.join(SCRIPT_DIR, "images", "bird1.png")
    gull_img_path = os.path.join(SCRIPT_DIR, "images", "gull1.png")

    # Effective sprite scale = base scale * GLOBAL_SCALE
    bird_scale = BIRD_BASE_SCALE * GLOBAL_SCALE

    # ---- Load / build base bird sprite ----
    if os.path.exists(bird_img_path):
        print(f"[Bird] Loading sprite from {bird_img_path}")
        bird_img_raw = pygame.image.load(bird_img_path).convert_alpha()

        # Scale with global zoom
        orig_w, orig_h = bird_img_raw.get_size()
        new_size = (int(orig_w * bird_scale), int(orig_h * bird_scale))

        # For pixel art you *might* prefer scale() (nearest neighbour);
        # smoothscale() will soften it a bit.
        bird_img = pygame.transform.smoothscale(bird_img_raw, new_size)
        # bird_img = pygame.transform.scale(bird_img_raw, new_size)
    else:
        print(f"[Bird] WARNING: {bird_img_path} not found. Using placeholder for BIRD.")
        placeholder = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.polygon(
            placeholder,
            (255, 0, 255, 255),
            [(20, 0), (0, 40), (40, 40)]
        )
        ph_w, ph_h = placeholder.get_size()
        ph_size = (int(ph_w * bird_scale), int(ph_h * bird_scale))
        bird_img = pygame.transform.smoothscale(placeholder, ph_size)

    # ---- Load / build seagull sprite ----
    gull_img = None
    if os.path.exists(gull_img_path):
        print(f"[Bird] Loading GULL sprite from {gull_img_path}")
        gull_img_raw = pygame.image.load(gull_img_path).convert_alpha()

        g_w, g_h = gull_img_raw.get_size()
        g_size = (int(g_w * bird_scale), int(g_h * bird_scale))
        gull_img = pygame.transform.smoothscale(gull_img_raw, g_size)
        # gull_img = pygame.transform.scale(gull_img_raw, g_size)
    else:
        print(f"[Bird] WARNING: {gull_img_path} not found. GULL trials will reuse bird sprite.")
        gull_img = bird_img  # fallback

    # Construct Bird with separate BIRD and GULL sprites
    bird = Bird(
        bird_image_surf=bird_img,
        gull_image_surf=gull_img,
        screen_w=int(w_csv),
        screen_h=int(h_csv),
        speed_px_s=200.0 * GLOBAL_SCALE,
        use_precision_timing=args.precision_rt,
    )

  
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
    bg_img_path = os.path.join(SCRIPT_DIR, "images", "ground1.png")

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

    completed_trials = 0

    def log_trial(outcome, record, feedback=None):
        nonlocal hits, misses, false_alarms, correct_rejects
        nonlocal nr_misses, pm_nr_misses, pm_hits, pm_misses, pm_false_alarms
        nonlocal completed_trials, running

        if feedback:
            feedback_list.append(FloatingFeedback(
                feedback["text"], feedback["color"],
                feedback["x"], feedback["y"],
                feedback["vx"], feedback["vy"]
            ))

        if record is not None:
            results_writer.writerow(record)
            results_file.flush()
            rt_app = record.get("rt_from_appearance", "")
            if isinstance(rt_app, (int, float)):
                all_rts.append(rt_app)

        if outcome is None:
            return

        if outcome == "HIT":
            hits += 1
        elif outcome == "MISS":
            misses += 1
        elif outcome == "FALSE_ALARM":
            false_alarms += 1
        elif outcome == "CORRECT_REJECT":
            correct_rejects += 1
        elif outcome == "NR":
            if record is not None and record.get("label") == "SEAGULL":
                pm_nr_misses += 1
            else:
                nr_misses += 1
        elif outcome == "GULL_HIT":
            pm_hits += 1
            rt_app = record.get("rt_from_appearance", "") if record is not None else ""
            if isinstance(rt_app, (int, float)):
                gull_rts.append(rt_app)
        elif outcome == "GULL_MISS":
            pm_misses += 1
        elif outcome == "GULL_FALSE_ALARM":
            pm_false_alarms += 1

        completed_trials += 1
        print("[Bird outcome]", outcome,
              f"(H={hits}, M={misses}, NR={nr_misses}, "
              f"FA={false_alarms}, CR={correct_rejects}, "
              f"pH={pm_hits}, pM={pm_misses}, pFA={pm_false_alarms})")

        if args.max_trials is not None and completed_trials >= args.max_trials:
            running = False

    def handle_key_response(response_type):
        if bird is None:
            return

        info = bird.register_response(response_type)
        if not info:
            return

        feedback = {
            "text": info["fb_text"],
            "color": info["fb_color"],
            "x": info["x"],
            "y": info["y"],
            "vx": info["vx"],
            "vy": info["vy"],
        }
        log_trial(info["outcome"], info["record"], feedback)
  
    running = True
    while running:
        # ---- Event handling (quit / ESC + discrete key presses) ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_c:
                    handle_key_response("THREAT")
                elif event.key == pygame.K_n:
                    handle_key_response("SAFE")
                elif event.key == pygame.K_9:
                    handle_key_response("SEAGULL")


        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0


        # Update bird motion, log trials, update counters & RT list
        if bird is not None:
            outcome, trial_record, fb = bird.update(dt)
            if outcome is not None or fb is not None:
                log_trial(outcome, trial_record, fb)



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
        
        # ---------- Compute background velocities --------------------------
        # With the player fixed at the display center, only the prevailing
        # wind contributes to background motion.
        wind_ang = math.radians(wind_bearing_deg)
        wind_vx = math.sin(wind_ang) * wind_speed_kn * WINDFIELD_PX_PER_KT
        wind_vy = -math.cos(wind_ang) * wind_speed_kn * WINDFIELD_PX_PER_KT
        wind_layer_vx = WIND_LAYER_WIND_WEIGHT * wind_vx
        wind_layer_vy = WIND_LAYER_WIND_WEIGHT * wind_vy

  
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
        
        
        # --------------- ACC / RT HUD (top-right, above compass) -------------
        # Recompute summary strings here to avoid scope issues

        # Main THREAT/SAFE accuracy & RT
        total_scored = hits + misses + false_alarms + correct_rejects + nr_misses
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

        # PM / GULL accuracy & RT
        pm_scored = pm_hits + pm_misses + pm_nr_misses
        if pm_scored > 0:
            pm_acc = pm_hits / pm_scored
            pm_acc_pct = pm_acc * 100.0
            pm_acc_str = f"PM ACC {pm_acc_pct:5.1f}%"
        else:
            pm_acc_str = "PM ACC --- %"

        if gull_rts:
            pm_mean_rt = sum(gull_rts) / len(gull_rts)
            pm_rt_str = f"PM MEAN RT {pm_mean_rt:.3f} s"
        else:
            pm_rt_str = "PM MEAN RT ---"

        hud_lines = [acc_str, mrt_str, pm_acc_str, pm_rt_str]
        hud_surfs = [font_small.render(line, True, TEXT_COLOR) for line in hud_lines]

        line_spacing = 4
        total_h = sum(s.get_height() for s in hud_surfs) + line_spacing * (len(hud_surfs) - 1)

        hud_center_x = compass_cx
        top_of_compass = compass_cy - COMPASS_RADIUS
        # Start a bit above the compass circle
        hud_y_start = max(10, top_of_compass - total_h - 40)

        y_cur = hud_y_start
        for surf in hud_surfs:
            rect = surf.get_rect(center=(hud_center_x, y_cur + surf.get_height() // 2))
            screen.blit(surf, rect)
            y_cur += surf.get_height() + line_spacing


  
        # ----------------------- Draw ownship circle -----------------------
        x = int(ownship["x_px"])
        y = int(ownship["y_px"])
        pygame.draw.circle(screen, CIRCLE_COLOR, (x, y), CIRCLE_RADIUS, 1)
        
        # ----------------------- Outcome bar charts & RT hist -----------------------
        # Left-hand panel: two bar charts (THREAT/SAFE, then PM) + two RT histograms

        panel_x = 10
        panel_w = 260

        bar_h   = 100   # height for each bar chart
        hist_h  = 80    # height for each histogram
        v_gap   = 10

        # ---- Main (THREAT/SAFE) accuracy & RT summaries -------------------
        total_scored = hits + misses + false_alarms + correct_rejects + nr_misses
        correct = hits + correct_rejects

        if total_scored > 0:
            acc = correct / total_scored
            acc_pct = acc * 100.0
        else:
            acc = None

        if all_rts:
            mean_rt = sum(all_rts) / len(all_rts)
        else:
            mean_rt = None

        # ---- PM / GULL accuracy & RT summaries ----------------------------
        pm_scored = pm_hits + pm_misses + pm_nr_misses
        if pm_scored > 0:
            pm_acc = pm_hits / pm_scored
            pm_acc_pct = pm_acc * 100.0
        else:
            pm_acc = None

        if gull_rts:
            pm_mean_rt = sum(gull_rts) / len(gull_rts)
        else:
            pm_mean_rt = None

        # ---- Layout for charts on the left (vertically centred) ----------
        total_block_h = 2 * bar_h + 2 * hist_h + 3 * v_gap
        block_top_y = (h - total_block_h) / 2  # centre the whole stack

        bar1_y   = int(block_top_y)
        bar1_rect = (panel_x, bar1_y, panel_w, bar_h)

        bar2_y   = bar1_y + bar_h + v_gap
        bar2_rect = (panel_x, bar2_y, panel_w, bar_h)

        hist1_y  = bar2_y + bar_h + v_gap
        hist1_rect = (panel_x, hist1_y, panel_w, hist_h)

        hist2_y  = hist1_y + hist_h + v_gap
        hist2_rect = (panel_x, hist2_y, panel_w, hist_h)

        # ---- THREAT/SAFE bar chart (H, M, NR, FA, CR) ---------------------
        outcome_counts_main = {
            "HIT":  hits,
            "MISS":  misses,
            "NR": nr_misses,
            "FA": false_alarms,
            "CR": correct_rejects,
        }
        prop_correct_main = acc if acc is not None else None

        draw_bar_chart(
            screen,
            font_small,   # axis font
            font_tiny,    # x-axis labels
            bar1_rect,
            outcome_counts_main,
            prop_correct=prop_correct_main,
        )

        # ---- PM / GULL bar chart (PM HIT / MISS / NR / FA) ----------------
        outcome_counts_pm = {
            "PM HIT":  pm_hits,
            "PM MISS":  pm_misses,
            "PM NR": pm_nr_misses,
            "PM FA": pm_false_alarms,
        }
        prop_correct_pm = pm_acc if pm_acc is not None else None

        draw_bar_chart(
            screen,
            font_small,
            font_tiny,
            bar2_rect,
            outcome_counts_pm,
            prop_correct=prop_correct_pm,
        )

        # ---- RT histogram (all RTs) with vertical mean line ----------------
        draw_rt_histogram(
            screen,
            font_small,
            hist1_rect,
            all_rts,
            mean_rt=mean_rt,
        )

        # ---- Second RT histogram (PM/GULL RTs only) ------------------------
        draw_rt_histogram(
            screen,
            font_small,
            hist2_rect,
            gull_rts,
            mean_rt=pm_mean_rt,
        )

        # Update & draw floating feedback
        to_remove = []
        for fb in feedback_list:
            if fb.update(dt):
                to_remove.append(fb)
            fb.draw(screen, font)

        for fb in to_remove:
            feedback_list.remove(fb)

        score_label = (f"HIT {hits}  MISS {misses}  "
                       f"FA {false_alarms}  CR {correct_rejects}  NR {nr_misses}  "
                       f"PM HIT {pm_hits}  PM MISS {pm_misses}  PM FA {pm_false_alarms}  PM NR {pm_nr_misses}")
        draw_text(
            screen,
            font,
            score_label,
            TEXT_COLOR,
            (w // 2, h - 30),  # bottom centre
        )

        # ------------------- Update ownship mood by accuracy -------------
        # Include NR for THREAT/SAFE birds in the denominator
        total_scored = hits + misses + false_alarms + correct_rejects + nr_misses
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
