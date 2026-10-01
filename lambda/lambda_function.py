import json
import random
import string
import boto3
from datetime import datetime, timezone
from botocore.exceptions import ClientError

TABLE = "urlshort-links"
dynamodb = boto3.client("dynamodb")
CHARS = string.ascii_letters + string.digits  # a-zA-Z0-9 = 62 options

def gen_short_id(length=6):
    return "".join(random.choices(CHARS, k=length))

def valid_url(url):
    return url.startswith("http://") or url.startswith("https://")

def respond(status, body, extra_headers=None):
    headers = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
    if extra_headers:
        headers.update(extra_headers)
    return {"statusCode": status, "headers": headers, "body": json.dumps(body) if isinstance(body, dict) else body}

def shorten(event):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON body"})

    long_url = body.get("long_url", "").strip()
    if not long_url:
        return respond(400, {"error": "long_url is required"})
    if not valid_url(long_url):
        return respond(400, {"error": "long_url must start with http:// or https://"})

    for _ in range(5):
        short_id = gen_short_id()
        try:
            dynamodb.put_item(
                TableName=TABLE,
                Item={
                    "short_id":   {"S": short_id},
                    "long_url":   {"S": long_url},
                    "created_at": {"S": datetime.now(timezone.utc).isoformat()},
                    "clicks":     {"N": "0"},
                },
                ConditionExpression="attribute_not_exists(short_id)"
            )
            return respond(200, {"short_id": short_id, "long_url": long_url})
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                continue
            return respond(500, {"error": str(e)})

    return respond(500, {"error": "Could not generate unique ID, try again"})

def redirect(event):
    short_id = (event.get("pathParameters") or {}).get("short_id", "").strip()
    if not short_id:
        return respond(400, {"error": "Missing short_id"})

    try:
        resp = dynamodb.get_item(TableName=TABLE, Key={"short_id": {"S": short_id}})
        item = resp.get("Item")
        if not item:
            return respond(404, {"error": "Short URL not found"})

        long_url = item["long_url"]["S"]

        try:
            dynamodb.update_item(
                TableName=TABLE,
                Key={"short_id": {"S": short_id}},
                UpdateExpression="ADD clicks :one",
                ExpressionAttributeValues={":one": {"N": "1"}}
            )
        except Exception:
            pass  # don't fail the redirect on counter errors

        return {
            "statusCode": 302,
            "headers": {
                "Location": long_url,
                "Access-Control-Allow-Origin": "*"
            },
            "body": ""
        }
    except ClientError as e:
        return respond(500, {"error": str(e)})

def lambda_handler(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "GET")
    path = http.get("path", "/")

    if method == "POST" and path == "/shorten":
        return shorten(event)

    if method == "GET":
        # Try path parameter first (API Gateway route)
        params = event.get("pathParameters") or {}
        if params.get("short_id"):
            return redirect(event)
        # Fallback: use the path itself (e.g., /abc123)
        if len(path) > 1:
            event["pathParameters"] = {"short_id": path.lstrip("/")}
            return redirect(event)

    return respond(404, {"error": "Not found"})
