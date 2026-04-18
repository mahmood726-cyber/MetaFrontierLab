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
  stop("Usage: Rscript metafor_trimfill_adapter.R <input_csv> <output_json>")
}

if (!requireNamespace("metafor", quietly = TRUE)) {
  write_json(args[2], "skipped", "metafor package is not installed.")
  quit(save = "no", status = 0)
}

dat <- read.csv(args[1], stringsAsFactors = FALSE)

fit <- tryCatch(
  {
    es <- metafor::escalc(
      measure = "OR",
      ai = dat$treat_events,
      bi = dat$treat_total - dat$treat_events,
      ci = dat$control_events,
      di = dat$control_total - dat$control_events,
      add = 0.5,
      to = "all"
    )
    res <- metafor::rma.uni(yi, vi, data = es, method = "DL")
    metafor::trimfill(res)
  },
  error = function(e) e
)

if (inherits(fit, "error")) {
  write_json(args[2], "error", conditionMessage(fit))
  quit(save = "no", status = 0)
}

estimate <- fit$b[[1]]
ci_low <- fit$ci.lb
ci_high <- fit$ci.ub
std_error <- sqrt(fit$vb[1, 1])
tau <- sqrt(fit$tau2)
if (!all_finite(estimate, std_error, ci_low, ci_high, tau)) {
  write_json(args[2], "error", "metafor trimfill returned non-finite estimates.")
  quit(save = "no", status = 0)
}
write_json(args[2], "ok", "metafor trimfill", estimate, std_error, ci_low, ci_high, tau)
