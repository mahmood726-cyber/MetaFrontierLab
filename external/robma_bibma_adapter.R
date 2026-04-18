args <- commandArgs(trailingOnly = TRUE)

escape_json <- function(x) {
  x <- gsub("\\\\", "\\\\\\\\", x)
  x <- gsub("\"", "\\\\\"", x)
  x <- gsub("\n", " ", x)
  x
}

write_json <- function(path, status, message, estimate = NA, std_error = NA, ci_low = NA, ci_high = NA, tau = NA) {
  payload <- sprintf(
    paste0(
      "{",
      "\"status\":\"%s\",",
      "\"message\":\"%s\",",
      "\"estimate\":%s,",
      "\"std_error\":%s,",
      "\"ci_low\":%s,",
      "\"ci_high\":%s,",
      "\"tau\":%s",
      "}\n"
    ),
    escape_json(status),
    escape_json(message),
    ifelse(is.na(estimate), "null", format(estimate, digits = 10, scientific = FALSE)),
    ifelse(is.na(std_error), "null", format(std_error, digits = 10, scientific = FALSE)),
    ifelse(is.na(ci_low), "null", format(ci_low, digits = 10, scientific = FALSE)),
    ifelse(is.na(ci_high), "null", format(ci_high, digits = 10, scientific = FALSE)),
    ifelse(is.na(tau), "null", format(tau, digits = 10, scientific = FALSE))
  )
  writeLines(payload, con = path, useBytes = TRUE)
}

all_finite <- function(...) {
  vals <- unlist(list(...))
  all(!is.na(vals) & is.finite(vals))
}

if (length(args) < 2) {
  stop("Usage: Rscript robma_bibma_adapter.R <input_csv> <output_json>")
}

input_csv <- args[1]
output_json <- args[2]

if (!requireNamespace("RoBMA", quietly = TRUE)) {
  write_json(output_json, "skipped", "RoBMA package is not installed in this R environment.")
  quit(save = "no", status = 0)
}

dat <- read.csv(input_csv, stringsAsFactors = FALSE)

fit <- tryCatch(
  RoBMA::BiBMA(
    x1 = dat$treat_events,
    x2 = dat$control_events,
    n1 = dat$treat_total,
    n2 = dat$control_total,
    study_names = dat$study,
    algorithm = "ss",
    seed = 1,
    silent = TRUE
  ),
  error = function(e) e
)

if (inherits(fit, "error")) {
  write_json(output_json, "error", conditionMessage(fit))
  quit(save = "no", status = 0)
}

summary_obj <- tryCatch(
  summary(fit, conditional = TRUE),
  error = function(e) e
)

if (inherits(summary_obj, "error")) {
  write_json(output_json, "error", conditionMessage(summary_obj))
  quit(save = "no", status = 0)
}

estimates <- tryCatch(as.data.frame(summary_obj$estimates_conditional), error = function(e) e)

if (inherits(estimates, "error")) {
  write_json(output_json, "error", conditionMessage(estimates))
  quit(save = "no", status = 0)
}

required_rows <- c("mu", "tau")
required_cols <- c("Mean", "0.025", "0.975")
if (!all(required_rows %in% rownames(estimates)) || !all(required_cols %in% colnames(estimates))) {
  write_json(output_json, "error", "RoBMA summary object did not contain the expected conditional estimate fields.")
  quit(save = "no", status = 0)
}

estimate <- as.numeric(estimates["mu", "Mean"])
ci_low <- as.numeric(estimates["mu", "0.025"])
ci_high <- as.numeric(estimates["mu", "0.975"])
std_error <- (ci_high - ci_low) / (2 * 1.96)
tau <- as.numeric(estimates["tau", "Mean"])

if (!all_finite(estimate, std_error, ci_low, ci_high, tau)) {
  write_json(output_json, "error", "RoBMA summary object returned non-finite conditional estimates.")
  quit(save = "no", status = 0)
}

write_json(
  output_json,
  "ok",
  "BiBMA conditional estimate extracted from the structured summary object.",
  estimate = estimate,
  std_error = std_error,
  ci_low = ci_low,
  ci_high = ci_high,
  tau = tau
)
