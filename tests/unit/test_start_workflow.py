import json

import pytest

from conftest import seed_order


@pytest.fixture
def handler(load_handler):
    return load_handler("start_workflow")


def sqs_event(*order_ids):
    return {
        "Records": [
            {
                "messageId": f"msg-{index}",
                "body": json.dumps({"orderId": order_id}),
                "attributes": {"ApproximateReceiveCount": "1"},
            }
            for index, order_id in enumerate(order_ids)
        ]
    }


def executions(aws):
    return aws.sfn.list_executions(stateMachineArn=aws.state_machine_arn)["executions"]


def test_starts_one_execution_named_after_the_order(aws, handler):
    order = seed_order(aws.orders)

    result = handler.lambda_handler(sqs_event(order["orderId"]), None)

    assert result == {"batchItemFailures": []}
    assert [e["name"] for e in executions(aws)] == [order["orderId"]]
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "PROCESSING"
    assert saved["executionArn"].endswith(f":execution:test-workflow:{order['orderId']}")


def test_duplicate_message_is_ignored(aws, handler):
    order = seed_order(aws.orders)

    handler.lambda_handler(sqs_event(order["orderId"]), None)
    result = handler.lambda_handler(sqs_event(order["orderId"], order["orderId"]), None)

    assert result == {"batchItemFailures": []}
    assert len(executions(aws)) == 1
    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert [h["status"] for h in saved["statusHistory"]].count("PROCESSING") == 1


def test_execution_already_exists_counts_as_success(aws, handler):
    order = seed_order(aws.orders)
    aws.sfn.start_execution(stateMachineArn=aws.state_machine_arn, name=order["orderId"], input="{}")

    result = handler.lambda_handler(sqs_event(order["orderId"]), None)

    assert result == {"batchItemFailures": []}
    assert len(executions(aws)) == 1


def test_processing_order_without_execution_is_recovered(aws, handler):
    """A previous attempt marked PROCESSING but StartExecution failed: the retry must start it."""
    order = seed_order(aws.orders, status="PROCESSING")

    handler.lambda_handler(sqs_event(order["orderId"]), None)

    assert [e["name"] for e in executions(aws)] == [order["orderId"]]


def test_poison_message_is_reported_as_batch_item_failure(aws, handler, capsys):
    good = seed_order(aws.orders)
    poison = seed_order(aws.orders, orderId="ORD-20261022-deadbeef", simulate="poison")

    result = handler.lambda_handler(sqs_event(good["orderId"], poison["orderId"]), None)

    # Only the poison message is retried; the good one in the same batch still succeeds.
    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-1"}]}
    assert [e["name"] for e in executions(aws)] == [good["orderId"]]
    assert aws.orders.get_item(Key={"orderId": poison["orderId"]})["Item"]["status"] == "PENDING"
    error_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"ERROR"' in line]
    assert error_lines[0]["orderId"] == poison["orderId"]
    assert error_lines[0]["errorType"] == "PoisonMessage"


def test_poison_deliveries_are_recorded_and_third_marks_dead_lettered(aws, handler):
    order = seed_order(aws.orders, simulate="poison")
    event = sqs_event(order["orderId"])

    for receive_count in ("1", "2", "3"):
        event["Records"][0]["attributes"]["ApproximateReceiveCount"] = receive_count
        handler.lambda_handler(event, None)

    saved = aws.orders.get_item(Key={"orderId": order["orderId"]})["Item"]
    assert saved["status"] == "PENDING"  # history-only events never change the status
    assert [h["status"] for h in saved["statusHistory"]] == [
        "PENDING",
        "DELIVERY_RETRY",
        "DELIVERY_RETRY",
        "DEAD_LETTERED",
    ]
    assert saved["deadLettered"] is True


def test_unknown_order_and_malformed_body_fail(aws, handler):
    event = sqs_event("ORD-20261022-00000000")
    event["Records"].append({"messageId": "bad", "body": "not json"})

    result = handler.lambda_handler(event, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-0"}, {"itemIdentifier": "bad"}]}
