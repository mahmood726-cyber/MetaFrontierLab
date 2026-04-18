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
  stop("Usage: Rscript copas_adapter.R <input_csv> <output_json>")
}

if (!requireNamespace("metasens", quietly = TRUE) || !requireNamespace("meta", quietly = TRUE)) {
  write_json(args[2], "skipped", "metasens/meta package is not installed.")
  quit(save = "no", status = 0)
}

dat <- read.csv(args[1], stringsAsFactors = FALSE)

fit <- tryCatch(
  {
    m <- meta::metabin(
      event.e = dat$treat_events,
      n.e = dat$treat_total,
      event.c = dat$control_events,
      n.c = dat$control_total,
      studlab = dat$study,
      sm = "OR",
      method = "Inverse",
      method.tau = "DL",
      incr = 0.5,
      method.incr = "all"
    )
    metasens::copas(m, silent = TRUE)
  },
  error = function(e) e
)

if (inherits(fit, "error")) {
  write_json(args[2], "error", conditionMessage(fit))
  quit(save = "no", status = 0)
}

estimate <- fit$TE.adjust
std_error <- fit$seTE.adjust
ci_low <- fit$lower.adjust
ci_high <- fit$upper.adjust
tau <- fit$tau.adjust
if (!all_finite(estimate, std_error, ci_low, ci_high, tau)) {
  write_json(args[2], "error", "Copas selection model returned non-finite estimates.")
  quit(save = "no", status = 0)
}
write_json(args[2], "ok", "metasens Copas selection model", estimate, std_error, ci_low, ci_high, tau)
