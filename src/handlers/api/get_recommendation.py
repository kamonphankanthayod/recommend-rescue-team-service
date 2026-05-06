# API Contract #7: Get Recommendation Detail

import os
import json
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from shared.utils.error_response import format_error_response

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ["REC_TABLE_NAME"])


def decimal_to_number(obj):
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    raise TypeError

def format_get_recommendation(item):
    ranked_teams = []

    for t in item.get("ranked_teams", []):
        breakdown = t.get("score_breakdown", {})

        ranked_teams.append({
            "rank": int(t.get("rank", 0)),
            "team_id": t.get("team_id"),
            "team_name": t.get("team_name"),
            "total_score": float(t.get("total_score", 0)),

            # FIX: ใช้ field ใหม่
            "score_breakdown": {
                "capability": float(breakdown.get("capability", 0)),
                "distance": float(breakdown.get("distance", 0)),
                "capacity": float(breakdown.get("capacity", 0)),
                "special_needs": float(breakdown.get("special_needs", 0)),
            },

            "explanation": t.get("explanation", "")
        })

    # confidence_score
    conf_score = item.get("confidence_score", Decimal("0"))
    formatted_conf_score = int(conf_score) if conf_score % 1 == 0 else float(conf_score)

    return {
        "recommendation_id": item.get("recommendation_id"),
        "request_id": item.get("request_id"),
        "incident_id": item.get("incident_id"),
        "recommendation_status": item.get("recommendation_status"),
        "confidence_score": formatted_conf_score,
        "ranked_teams": ranked_teams,
        "model_version": item.get("model_version", ""),
        "evaluated_at": item.get("evaluated_at", ""),
        "created_at": item.get("created_at", "")
    }

def get_recommendation_by_request_id(event):
    # HttpApi แบบ $default จะซ่อน requestId ไว้ใน requestContext
    req_context = event.get("requestContext", {})
    trace_id = req_context.get("requestId", "UNKNOWN_TRACE_ID")
    
    # -------------------------------------------------------------
    # การดึง request_id รองรับทั้งแบบระบุ Path และแบบ $default
    # -------------------------------------------------------------
    request_id = None
    path_params = event.get("pathParameters")
    
    if path_params and "request_id" in path_params:
        # กรณีตั้งค่า Route แบบระบุตัวแปรใน API Gateway
        request_id = path_params["request_id"]
    else:
        # กรณีใช้ $default Route ให้ตัดคำจาก rawPath แทน
        raw_path = event.get("rawPath", "") # เช่น "/v1/recommendations/219d078a-5c63-4387-a3bf-6f61e2c9c6aa"
        parts = raw_path.strip("/").split("/") # จะได้ ['v1', 'recommendations', '219d078a-5c63-4387-a3bf-6f61e2c9c6aa']
        
        # ตรวจสอบว่า path ถูกต้องและมีตำแหน่งของ request_id
        if len(parts) >= 4 and parts[-2] == "recommendations":
            request_id = parts[-1]

    print(f"[{trace_id}] START --- GET /v1/recommendations/{request_id}")

    try:
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
        
        response = table.query(
            IndexName="request_id-index",
            KeyConditionExpression=Key("request_id").eq(request_id)
        )

        items = response.get("Items", [])

        ## Error: 404 Not Found
        if not items:
            print(f"[{trace_id}] 404 REFERENCE_NOT_FOUND - No recommendation found for request_id: {request_id}")
            return format_error_response(
                404,
                "REFERENCE_NOT_FOUND",
                "recommendation not found for request_id",
                trace_id
            )

        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        latest_item = items[0]

        print(f"[{trace_id}] Found {len(items)} versions. Picking the latest one: {latest_item.get('recommendation_id')}")

        item = format_get_recommendation(latest_item)
        # print(f"[{trace_id}] Data: {json.dumps(item, default=decimal_to_number)}")
        
        ## Success: 200 Success
        print(f"[{trace_id}] 200 Success - Get recommendation success for request_id: {request_id}")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(item, default=decimal_to_number)
        }

    ## Error: 500 INTERNAL_SERVER_ERROR
    except Exception as e:
        print(f"[{trace_id}] 500 INTERNAL_SERVER_ERROR - Error: {str(e)}")
        return format_error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            "Fail to get recommendation detail",
            trace_id
        )