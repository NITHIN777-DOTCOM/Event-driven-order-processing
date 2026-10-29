# terraform -chdir=infra/modules/tag_values init && terraform -chdir=infra/modules/tag_values test
# Proves that an invalid tag value fails at PLAN time (no AWS access: the module has no resources).

run "accepts_the_allowed_character_set" {
  command = plan

  variables {
    descriptions = {
      plain   = "Order saga - reserve inventory - request payment and wait up to 120 s"
      symbols = "a_b.c:d=e+f-g@h"
      unicode = "Bestellungen für Kunden"
      empty   = ""
    }
  }

  assert {
    condition     = output.description["symbols"] == "a_b.c:d=e+f-g@h"
    error_message = "valid values must pass through unchanged"
  }
}

# The exact value that broke step 2.1's deploy on the state machine.
run "rejects_parentheses" {
  command = plan

  variables {
    descriptions = {
      state_machine = "request payment and wait for the signed webhook (120 s timeout)"
    }
  }

  expect_failures = [var.descriptions]
}

# DynamoDB accepts "/", Step Functions does not: the strictest set wins.
run "rejects_slash" {
  command = plan

  variables {
    descriptions = { queue = "orders/payments" }
  }

  expect_failures = [var.descriptions]
}

run "rejects_comma_and_middle_dot" {
  command = plan

  variables {
    descriptions = { a = "stock, reserved", b = "API · webhook" }
  }

  expect_failures = [var.descriptions]
}

run "rejects_more_than_256_characters" {
  command = plan

  variables {
    descriptions = { long = "x${join("", [for i in range(256) : "y"])}" }
  }

  expect_failures = [var.descriptions]
}
