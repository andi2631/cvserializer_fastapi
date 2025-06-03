from app import process_cv_text
import json

def lambda_handler(event, context):
    try:
        body = json.loads(event["body"])
        text = body.get("text", "")
        result = process_cv_text(text)
        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
