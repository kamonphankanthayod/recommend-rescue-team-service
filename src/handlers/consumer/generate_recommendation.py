import os
import json
import uuid
import time
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

from shared.utils.hash import hash_body

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["REC_TABLE_NAME"])

lambda_client = boto3.client("lambda")
cloudwatch = boto3.client("cloudwatch")

INITIAL_STATUS = "PENDING"
MAX_WORKER_RETRY = 3


# -------------------------
# CloudWatch Metrics
# -------------------------
def put_metric(name, value=1):
    try:
        cloudwatch.put_metric_data(
            Namespace="RescueTeamService",
            MetricData=[{
                "MetricName": name,
                "Value": value,
                "Unit": "Count"
            }]
        )
    except Exception:
        pass


# -------------------------
# Worker invoke (retry)
# -------------------------
def invoke_worker_with_retry(payload, trace_id):
    worker_lambda = os.environ["WORKER_LAMBDA_NAME"]

    for attempt in range(1, MAX_WORKER_RETRY + 1):
        try:
            lambda_client.invoke(
                FunctionName=worker_lambda,
                InvocationType="Event",
                Payload=json.dumps(payload)
            )

            print(f"[{trace_id}] Worker invoked (attempt {attempt})")
            put_metric("WorkerInvokeSuccess")
            return True

        except Exception as e:
            print(f"[{trace_id}] Worker invoke failed {attempt}: {str(e)}")
            put_metric("WorkerInvokeFailure")
            time.sleep(2 ** attempt)

    return False


# -------------------------
# Main Logic
# -------------------------
def generate_recommendation(event):
    print(f"Received event: {json.dumps(event)}")
    header = event.get("header", {})
    body = event.get("body", {})

    trace_id = header.get("traceId", "unknown-trace")

    print(f"[{trace_id}] START generate_recommendation")

    request_id = body["requestId"]
    incident_id = body["incidentId"]
    evaluate_id = body["evaluateId"]

    recommendation_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

    item = {
        "recommendation_id": recommendation_id,
        "request_id": request_id,
        "incident_id": incident_id,
        "recommendation_status": INITIAL_STATUS,
        "created_at": now,
        "updated_at": now,
        "idempotency_key": evaluate_id,
        "request_hash": hash_body(body)
    }

    # -------------------------
    # 1. Idempotency (Atomic)
    # -------------------------
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(idempotency_key)"
        )
        print(f"[{trace_id}] Created recommendation {recommendation_id}")
        put_metric("RecommendationCreated")

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            print(f"[{trace_id}] Duplicate event -> skip")
            put_metric("DuplicateEvent")
            return
        else:
            put_metric("DynamoDBError")
            raise

    # -------------------------
    # 2. Supersede old
    # -------------------------
    try:
        response = table.query(
            IndexName="request_id-index",
            KeyConditionExpression=Key("request_id").eq(request_id)
        )

        active_statuses = {"PENDING", "CALCULATING", "GENERATED"}

        for old in response.get("Items", []):
            if old["recommendation_id"] == recommendation_id:
                continue

            if old.get("recommendation_status") in active_statuses:
                table.update_item(
                    Key={"recommendation_id": old["recommendation_id"]},
                    UpdateExpression="SET recommendation_status = :s, updated_at = :u",
                    ExpressionAttributeValues={
                        ":s": "SUPERSEDED",
                        ":u": now
                    }
                )

                print(f"[{trace_id}] Superseded {old['recommendation_id']}")
                put_metric("RecommendationSuperseded")

    except Exception as e:
        print(f"[{trace_id}] WARNING supersede failed: {str(e)}")
        put_metric("SupersedeError")

    # -------------------------
    # 3. Invoke worker
    # -------------------------
    #evaluate_id, request_type, priority_level, evaluate_reason, location, people_count, special_needs
    worker_payload = {
        "recommendation_id": recommendation_id,
        "request_id": request_id,
        "incident_id": incident_id,
        "request_type": body.get("requestType"),
        "incident_type": body.get("incidentType"),
        "priority": body.get("priorityScore"),
        "location": body.get("location"),
        "people_count": body.get("peopleCount"),
        "special_needs": body.get("specialNeeds"),
        "trace_id": trace_id,
        "created_at": now,
        "evaluate_id": evaluate_id,
        "evaluate_reason": body.get("evaluateReason"),
        "priority_level": body.get("priorityLevel")
    }

    success = invoke_worker_with_retry(worker_payload, trace_id)

    if not success:
        print(f"[{trace_id}] Worker failed permanently")
        put_metric("WorkerInvokePermanentFailure")

        table.update_item(
            Key={"recommendation_id": recommendation_id},
            UpdateExpression="SET recommendation_status = :s",
            ExpressionAttributeValues={":s": "FAILED"}
        )

    print(f"[{trace_id}] DONE handler/consumer/generate_recommendation.py")