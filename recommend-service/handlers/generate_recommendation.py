# POST method for generate recommendation

import os
import json
import uuid   # use for generate new recommendation_id
from datetime import datetime   # use for generate new recommendation
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

# for external services
from services.rescue_request_service import get_rescue_request
from services.incident_service import get_incident

from utils.error_response import format_error_response
from utils.validator import is_valid_uuid
from utils.hash import hash_body

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["TABLE_NAME"])    #TABLE_NAME = "recommendations"

lambda_client = boto3.client('lambda')

fixed_init_recommendation_status = "PENDING"   # Lifecycle: PENDING / CALCULATING / GENERATED / FAILED / EXPIRED


def format_generate_recommendation(item):
    return {
        "recommendation_id": item["recommendation_id"],
        "request_id": item["request_id"],
        "incident_id": item["incident_id"],
        "recommendation_status": item["recommendation_status"],
        "created_at": item["created_at"]
    }

def generate_recommendation(event):
    trace_id = event["requestContext"]["requestId"]
    print(f"[{trace_id}] START --- POST /v1/recommendations")

    try:
        print(f"[{trace_id}] Parsing request data - Header, Body")
        headers = event.get("headers", {})
        idempotency_key = headers.get("idempotency-key")
        body = json.loads(event.get("body", "{}"))
        print(f"[{trace_id}] Headers: {json.dumps(headers)}")
        print(f"[{trace_id}] Idempotency-Key: {idempotency_key}")
        print(f"[{trace_id}] Body: {json.dumps(body)}")

        ## Validation Header Error: 400 Bad Request
        if not idempotency_key:
            print(f"[{trace_id}] 400 VALIDATION_HEADER_ERROR - Idempotency-Key is required")
            return format_error_response(
                400,
                "VALIDATION_HEADER_ERROR",
                "Idempotency-Key is required",
                trace_id,
                [{"field": "idempotency_key", "issue": "missing"}]
            )

        ## Validation Header Error: 400 Bad Request
        if not is_valid_uuid(idempotency_key):
            print(f"[{trace_id}] 400 VALIDATION_HEADER_ERROR - Invalid idempotency_key format")
            return format_error_response(
                400,
                "VALIDATION_HEADER_ERROR",
                "Invalid idempotency_key format - Idempotency-Key must be a valid UUID",
                trace_id,
                [{"field": "idempotency_key", "issue": "invalid_format"}]
            )

        # Check if the idempotency key is already used
        print(f"[{trace_id}] Checking for existing recommendation with idempotency key: {idempotency_key}")
        response = table.query(
            IndexName="idempotency_key-index",
            KeyConditionExpression=Key("idempotency_key").eq(idempotency_key),
            Limit=1
        )

        items = response.get("Items", [])
        
        print(f"[{trace_id}] Existing items count: {len(items)}, Items: {items}")
        ## Error: 500 INTERNAL_SERVER_ERROR
        if len(items) > 1:
            print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - Multiple items found with same idempotency key")
            return format_error_response(
                500,
                "INTERNAL_SERVER_ERROR",
                "Multiple recommendations found with same idempotency key",
                trace_id
            )

        if items:
            ## Error: 409 Conflict - Key same but body not same
            existing = items[0]
            if existing["request_hash"] != hash_body(body):
                print(f"[{trace_id}] 409 CONFLICT - Idempotency-Key already used with different payload")
                return format_error_response(
                    409,
                    "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD",
                    "Same Idempotency-Key used with different request body",
                    trace_id
            )

            ## 200 Success - Key same and body same
            print(f"[{trace_id}] 200 Success - Idempotent replay")
            response_item = format_generate_recommendation(items[0])
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(response_item)
            }


        # If not Idempotency-Key Goooo!!!
        print(f"[{trace_id}] Idempotency-Key not found. Processing new request.")
        
        request_id = body.get("request_id")
        force_reevaluate = body.get("force_reevaluate", False)

        ## Validation Error: 400 Bad Request
        if not request_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - request_id is required")
            return format_error_response(
                400,
                "VALIDATION_ERROR",
                "request_id is required",
                trace_id,
                [{"field": "request_id", "issue": "missing"}]
            )

        # ค้นหา Recommendation เดิมของ request_id นี้
        response_req = table.query(
            IndexName="request_id-index",
            KeyConditionExpression=Key("request_id").eq(request_id)
            # Limit=1
        )
        existing_items = response_req.get("Items", [])

        # กรองหาเฉพาะตัวที่กำลัง "Active" อยู่
        active_statuses = ["PENDING", "CALCULATING", "GENERATED"]
        active_items = [item for item in existing_items if item.get("recommendation_status") in active_statuses]

        if active_items:
            # กรณีที่ 1: มีของเดิมอยู่แต่ไม่ได้สั่งบังคับทำใหม่ (force_reevaluate = False)
            if not force_reevaluate:
                print(f"[{trace_id}] 409 CONFLICT - Active recommendation already exists for request: {request_id}")
                return format_error_response(
                    409, 
                    "ACTIVE_RECOMMENDATION_EXISTS", 
                    "An active recommendation already exists. Set 'force_reevaluate' to true to override.", 
                    trace_id
                )
            
            # กรณีที่ 2: มีของเดิมอยู่และสั่งบังคับทำใหม่ (force_reevaluate = True)
            print(f"[{trace_id}] Force reevaluate triggered. Superseding old recommendations.")
            for old_item in active_items:
                old_id = old_item['recommendation_id']
                try:
                    # เปลี่ยนสถานะของเก่าให้เป็น SUPERSEDED เพื่อเก็บเป็น Audit Trail
                    table.update_item(
                        Key={'recommendation_id': old_id},
                        UpdateExpression="SET recommendation_status = :s, updated_at = :ua",
                        ExpressionAttributeValues={
                            ':s': 'SUPERSEDED',
                            ':ua': datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
                        }
                    )
                    print(f"[{trace_id}] Superseded recommendation_id: {old_id}")
                except Exception as e:
                    print(f"[{trace_id}] Failed to supersede {old_id}: {str(e)}")

        
        # Call external service (mock/real) 
        rescue_data = get_rescue_request(request_id, trace_id)

        ## Error: 404 Not Found
        if not rescue_data:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - Rescue request not found for ID: {request_id}")
            return format_error_response(
                404,
                "REFERENCE_NOT_FOUND",
                "request_id not found",
                trace_id
            )

        incident_id = rescue_data["request"]["incidentId"]

        # start process to generate new recommendation
        print(f"[{trace_id}] Creating NEW recommendation for request: {request_id}")

        # new_recommendation_id
        new_recommendation_id = str(uuid.uuid4())

        item = {
            "recommendation_id": new_recommendation_id,
            "request_id": request_id,
            "incident_id": incident_id,
            "recommendation_status": fixed_init_recommendation_status,   # PENDING
            "created_at": datetime.utcnow().isoformat(timespec='milliseconds') + "Z",
            "idempotency_key": idempotency_key,
            "request_hash": hash_body(body)
        }
        table.put_item(Item=item)

        # Asynchronous Invoke ไปยัง Lambda B (Scoring Worker)
        worker_payload = {
            "recommendation_id": new_recommendation_id,
            "request_id": request_id,
            "incident_id": incident_id,
            "trace_id": trace_id # ส่ง trace_id ไปด้วยเพื่อให้ไล่ log ง่าย
        }

        try:
            # อย่าลืมเพิ่ม WORKER_LAMBDA_NAME ใน Environment Variables ของ Lambda A ด้วย
            worker_lambda_name = os.environ.get("WORKER_LAMBDA_NAME") 
            
            print(f"[{trace_id}] Asynchronously invoking worker lambda: {worker_lambda_name}")
            lambda_client.invoke(
                FunctionName=worker_lambda_name,
                InvocationType='Event', # สำคัญมาก 'Event' แปลว่า Fire and Forget (Async)
                Payload=json.dumps(worker_payload)
            )
        except Exception as invoke_err:
            # แค่พิมพ์ Log ไว้ แต่ไม่บล็อกการทำงาน เพราะถือว่ารับงานลง DB แล้ว
            # (ในอนาคตอาจจะมีกลไก Retry ถ้า Invoke พลาด)
            print(f"[{trace_id}] WARNING - Failed to invoke worker lambda: {str(invoke_err)}")
        
        print(f"[{trace_id}] This is NOT a failure. Recommendation {new_recommendation_id} is already saved in DB.")


        response_item = format_generate_recommendation(item)

        ## Success: 202 Accepted
        print(f"[{trace_id}] 202 Accepted - Queued recommendation with ID: {new_recommendation_id}")

        return {
            "statusCode": 202,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(response_item)
        }

    ## Error: 500 INTERNAL_SERVER_ERROR
    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - Error: {str(e)}")
        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Failed to create recommendation",
            trace_id
        )