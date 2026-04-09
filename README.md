# Swoop

Swoop is a small Pygame-based experimental task about fast visual threat detection. The player monitors a central circular display while moving bird stimuli approach on different trajectories and must decide quickly whether each target is a threat, safe, or a seagull oddball.

The game is designed to capture response accuracy and reaction time under time pressure. It records trial-by-trial outcomes to CSV, including whether responses were correct, missed, false alarms, or too slow.

The current project keeps a single precision-timed Python implementation at `python/swoop.py`, with an R launcher in `1-run.R` for running it through `reticulate`.

Quick start:

- Run `0-setup_pygame.R` once to create the `r-pygame` conda environment and install `pygame`.
- Run `1-run.R` to launch the task through `reticulate`.
- For a non-interactive smoke test, run `python3 python/swoop.py --headless --max-trials 5`.

Results are written to `output/results_swoop_precision_rt.csv` in the repo root by default.

Basic controls:

- `C`: respond `THREAT`
- `N`: respond `SAFE`
- `9`: respond `SEAGULL`
- `Esc`: quit
