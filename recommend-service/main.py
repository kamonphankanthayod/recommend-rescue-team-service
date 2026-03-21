import json

from handlers.generate_recommendation import generate_recommendation
from handlers.get_recommendation import get_recommendation_by_request_id
from handlers.delete_recommendation import delete_recommendation
from handlers.update_recommendation import update_recommendation_status

from utils.auth import authorize_dispatcher
from utils.error_response import format_error_response

def lambda_handler(event, context):
    trace_id = event["requestContext"].get("requestId", "unknown-trace-id")
    
    print(json.dumps(event))

    path = event["rawPath"]     # "/v1/recommendations"
    method = event["requestContext"]["http"]["method"]     # "POST" || "GET" || "DELETE" || "PATCH"

    print(f"[{trace_id}] Received {method} request for path: {path}")

    # AUTHORIZATION MIDDLEWARE
    is_authorized, auth_error_msg = authorize_dispatcher(event)
    if not is_authorized:
        print(f"[{trace_id}] 401 UNAUTHORIZED - {auth_error_msg}")
        return format_error_response(
            401, 
            "UNAUTHORIZED", 
            auth_error_msg, 
            trace_id
        )
        
    print(f"[{trace_id}] Request authorized successfully")

    if path == "/v1/recommendations" and method == "POST":
        return generate_recommendation(event)

    if path.startswith("/v1/recommendations/") and path.endswith("/status") and method == "PATCH":
        return update_recommendation_status(event)

    if path.startswith("/v1/recommendations/") and method == "GET":
        return get_recommendation_by_request_id(event)

    if path.startswith("/v1/recommendations/") and method == "DELETE":
        return delete_recommendation(event)

    return {
        "statusCode": 404,
        "body": "Not Found"
    }