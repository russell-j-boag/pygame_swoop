# setup.R
rm(list = ls())

library("reticulate")

## 1) Make sure reticulate's miniconda exists (or create it)
mc_path <- miniconda_path()

if (!dir.exists(mc_path)) {
  message("No Miniconda found at: ", mc_path, "\nInstalling Miniconda via reticulate...")
  install_miniconda()
} else {
  message("Miniconda found at: ", mc_path)
}

## 2) Create a new env for pygame (if it doesn't already exist)
env_name <- "r-pygame"

envs <- conda_list()$name
if (!(env_name %in% envs)) {
  message("Creating conda env '", env_name, "' with python + pip...")
  conda_create(
    envname  = env_name,
    packages = c("python=3.11", "pip"),
    forge    = TRUE
  )
} else {
  message("Conda env '", env_name, "' already exists.")
}

## 3) Install Pygame into that env
message("Installing pygame into '", env_name, "'...")
conda_install(
  envname  = env_name,
  packages = "pygame",
  forge    = TRUE
)

## 4) Point reticulate at that env and show config
use_condaenv(env_name, required = TRUE)
py_config()
