import json
import uuid
import boto3
import os
import hashlib
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key

from services.rescue_request_service import get_rescue_request
from services.incident_service import get_incident

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["TABLE_NAME"])    #TABLE_NAME = "recommendations"

def format_recommendation(item):
    return {
        "recommendation_id": item["recommendation_id"],
        "request_id": item["request_id"],
        "recommendation_status": item["recommendation_status"],
        "confidence_score": float(item["confidence_score"]),
        "ranked_teams": [
            {
                "team_id": t["team_id"],
                "rank": t["rank"],
                "total_score": float(t["total_score"]),
                "score_breakdown": {
                    "specialization_score": float(t["score_breakdown"]["specialization_score"]),
                    "distance_score": float(t["score_breakdown"]["distance_score"]),
                    "availability_score": float(t["score_breakdown"]["availability_score"]),
                    "severity_weight": float(t["score_breakdown"]["severity_weight"]),
                },
                "explanation": t["explanation"]
            }
            for t in item.get("ranked_teams", [])
        ],
        "model_version": item["model_version"],
        "evaluated_at": item["evaluated_at"]
    }

def format_create_recommendation(item):
    return {
        "recommendation_id": item["recommendation_id"],
        "request_id": item["request_id"],
        "incident_id": item["incident_id"],
        "recommendation_status": item["recommendation_status"],
        "created_at": item["created_at"]
    }

def build_error(status_code, code, message, trace_id, details=None):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "error": {
                "code": code,
                "message": message,
                "trace_id": trace_id,
                "details": details or []
            }
        })
    }

def decimal_to_float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def is_valid_uuid(val):
    try:
        uuid.UUID(val)
        return True
    except:
        return False

def hash_body(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def lambda_handler(event, context):
    print(json.dumps(event))
    path = event["rawPath"]     # "/v1/recommendations" ||| 
    method = event["requestContext"]["http"]["method"]     # "POST" ||| "GET"
    print(f"Received {method} request for path: {path}")

    if path == "/v1/recommendations" and method == "POST":
        return create_recommendation(event)

    if path.startswith("/v1/recommendations/") and method == "GET":
        return get_recommendation_by_request_id(event)

    return {
        "statusCode": 404,
        "body": "Not Found"
    }


def create_recommendation(event):
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
            return build_error(
                400,
                "VALIDATION_HEADER_ERROR",
                "Idempotency-Key is required",
                trace_id,
                [{"field": "idempotency_key", "issue": "missing"}]
            )

        ## Validation Header Error: 400 Bad Request
        if not is_valid_uuid(idempotency_key):
            print(f"[{trace_id}] 400 VALIDATION_HEADER_ERROR - Invalid idempotency_key format")
            return build_error(
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
            return build_error(
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
                return build_error(
                    409,
                    "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD",
                    "Same Idempotency-Key used with different request body",
                    trace_id
            )

            ## 200 Success - Key same and body same
            print(f"[{trace_id}] 200 Success - Idempotent replay")
            response_item = format_create_recommendation(items[0])
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(response_item, default=decimal_to_float)
            }


        # If not Idempotency-Key Goooo!!!
        print(f"[{trace_id}] Idempotency-Key not found. Processing new request.")
        
        request_id = body.get("request_id")

        ## Validation Error: 400 Bad Request
        if not request_id:
            print(f"[{trace_id}] 400 VALIDATION_ERROR - request_id is required")
            return build_error(
                400,
                "VALIDATION_ERROR",
                "request_id is required",
                trace_id,
                [{"field": "request_id", "issue": "missing"}]
            )

        response_req = table.query(
            IndexName="request_id-index",
            KeyConditionExpression=Key("request_id").eq(request_id),
            Limit=1
        )

        existing_items = response_req.get("Items", [])
        
        if existing_items:
            print(f"[{trace_id}] 200 Success - Recommendation already exists for request: {request_id}")
            response_item = format_create_recommendation(existing_items[0])
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(response_item, default=decimal_to_float)
            }


        # Call external service (mock/real) 
        rescue_data = get_rescue_request(request_id, trace_id)
        #print(json.dumps(rescue_data))

        ## Error: 404 Not Found
        if not rescue_data:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - Rescue request not found for ID: {request_id}")
            return build_error(
                404,
                "REFERENCE_NOT_FOUND",
                "request_id not found",
                trace_id
            )

        incident_id = rescue_data["request"]["incidentId"]
        #incident_data = get_incident(incident_id, trace_id)
        #print(json.dumps(incident_data))

        # logic to generate recommendation
        print(f"[{trace_id}] Creating recommendation for request: {request_id}")

        # (ตรงนี้ในอนาคตใช้ rescue_data มาคำนวณจริง)
        recommendation_id = str(uuid.uuid4())

        item = {
            "recommendation_id": recommendation_id,
            "request_id": request_id,
            "incident_id": incident_id,
            "recommendation_status": "GENERATED",
            "confidence_score": Decimal("4.0"),
            "ranked_teams": [
                {
                    "team_id": "TEAM-01",
                    "rank": 1,
                    "total_score": Decimal("87.5"),
                    "score_breakdown": {
                        "specialization_score": Decimal("30.0"),
                        "distance_score": Decimal("25.0"),
                        "availability_score": Decimal("20.0"),
                        "severity_weight": Decimal("12.5")
                    },
                    "explanation": "Team specialization matches fire response"
                }
            ],
            "model_version": "v1.0.0",
            "created_at": datetime.utcnow().isoformat(timespec='milliseconds') + "Z",
            "evaluated_at": datetime.utcnow().isoformat(timespec='milliseconds') + "Z",
            "idempotency_key": idempotency_key,
            "request_hash": hash_body(body)
        }

        table.put_item(Item=item)

        response_item = format_create_recommendation(item)

        ## Success: 201 Created
        print(f"[{trace_id}] 201 Created - Created recommendation with ID: {recommendation_id}")

        return {
            "statusCode": 201,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(response_item, default=decimal_to_float)
        }

    ## Error: 500 INTERNAL_SERVER_ERROR
    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - Error: {str(e)}")
        return build_error(
            500,
            "INTERNAL_SERVER_ERROR",
            "Failed to create recommendation",
            trace_id
        )


def get_recommendation_by_request_id(event):
    trace_id = event["requestContext"]["requestId"]
    print(f"[{trace_id}] START --- GET /v1/recommendations/{event['pathParameters']['request_id']}")

    try:
        request_id = event["pathParameters"]["request_id"]
    
        #print(f"Fetching recommendations for request_id: {request_id}")

        response = table.query(
            IndexName="request_id-index",
            KeyConditionExpression=Key("request_id").eq(request_id)
        )

        items = response.get("Items", [])

        ## Error: 404 Not Found
        if not items:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - No recommendation found for request_id: {request_id}")
            return build_error(
                404,
                "REFERENCE_NOT_FOUND",
                "recommendation not found for request_id",
                trace_id
            )

        #print("Items:", items)
        #print(f"Found {len(items)} recommendation(s) for request_id: {request_id}")

        item = format_recommendation(items[0])
        print(f"[{trace_id}] Data: {json.dumps(item, default=decimal_to_float)}")
        
        ## Success: 200 Success
        print(f"[{trace_id}] 200 Success - Get recommendation success for request_id: {request_id}")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(item, default=decimal_to_float)
        }

    ## Error: 500 INTERNAL_SERVER_ERROR
    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - Error: {str(e)}")
        return build_error(
            500,
            "INTERNAL_SERVER_ERROR",
            "Fail to get recommendation detail",
            trace_id
        )