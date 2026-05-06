import json

from handlers.api.get_available_teams import get_available_teams
from handlers.api.create_team import create_team
from handlers.api.get_team_detail import get_team_detail
from handlers.api.delete_team import delete_team
from handlers.api.update_team_status import update_team_status

from handlers.api.get_recommendation import get_recommendation_by_request_id
from handlers.api.delete_recommendation import delete_recommendation
from handlers.api.update_recommendation import update_recommendation_status

from shared.utils.auth import authorize_dispatcher
from shared.utils.error_response import format_error_response

def lambda_handler(event, context):
    trace_id = event["requestContext"].get("requestId", "unknown-trace-id")
    # print(json.dumps(event))

    path = event["rawPath"]     # "/v1/recommendations"
    method = event["requestContext"]["http"]["method"]     # "POST" || "GET" || "DELETE" || "PATCH"

    print(f"[{trace_id}] Received {method} request for path: {path}")

    # --- จัดการ CORS Preflight ---
    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,Authorization"
            }
        }
    
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

    if path == "/v1/teams" and method == "GET":
        return get_available_teams(event)

    if path == "/v1/teams" and method == "POST":
        return create_team(event)

    if path.startswith("/v1/teams/") and path.endswith("/status") and method == "PATCH":
        return update_team_status(event)
        
    if path.startswith("/v1/teams/") and method == "GET":
        return get_team_detail(event)

    if path.startswith("/v1/teams/") and method == "DELETE":
        return delete_team(event)


    if path.startswith("/v1/recommendations/") and path.endswith("/status") and method == "PATCH":
        return update_recommendation_status(event)

    if path.startswith("/v1/recommendations/") and method == "GET":
        return get_recommendation_by_request_id(event)

    if path.startswith("/v1/recommendations/") and method == "DELETE":
        return delete_recommendation(event)

    return {
        "statusCode": 404,
        "body": "Not Found ja"
    }