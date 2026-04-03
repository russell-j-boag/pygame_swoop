rm(list = ls())

run_swoop <- function(
    conda_env    = "r-pygame",
    atclab_script = "python/swoop.py",
    extra_args   = NULL
) {
  # Script must exist
  stopifnot(file.exists(atclab_script))
  
  # Load reticulate + activate env
  if (!requireNamespace("reticulate", quietly = TRUE)) {
    stop("Package 'reticulate' is required but not installed.")
  }
  reticulate::use_condaenv(conda_env, required = TRUE)
  
  # Python binary
  py_bin <- reticulate::py_config()$python
  message("Using Python: ", py_bin)
  
  # Base args: always the script
  args <- c(atclab_script)
  
  # Optional passthrough arguments
  if (!is.null(extra_args)) {
    stopifnot(is.character(extra_args))
    args <- c(args, extra_args)
  }
  
  # Run the sim
  status <- system2(py_bin, args)
  invisible(status)
}

run_swoop()
