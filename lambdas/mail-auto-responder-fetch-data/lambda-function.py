import json
import os
import boto3
from datetime import datetime, timezone, timedelta
from collections import defaultdict

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['TABLE_NAME']


def lambda_handler(event, context):

    table = dynamodb.Table(TABLE_NAME)

    try:
        response = table.scan()
        items = response.get('Items', [])

        # Sort newest first
        items.sort(
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )

        processed = 0
        failed = 0
        auto_replies = 0
        today_count = 0

        weekly_data = [0] * 7
        keyword_distribution = defaultdict(int)

        today = datetime.now(timezone.utc).date()

        for item in items:

            status = item.get("status")
            auto_reply = item.get("auto_reply", False)
            keyword = item.get("keyword")
            timestamp = item.get("timestamp")

            # Count processed / failed
            if status == "Processed":
                processed += 1
            elif status == "Failed":
                failed += 1

            # Count auto replies
            if auto_reply is True:
                auto_replies += 1

            # Keyword distribution
            if keyword:
                keyword_distribution[keyword] += 1

            # Today + weekly count
            if timestamp:
                try:
                    email_date = datetime.fromisoformat(timestamp).date()

                    if email_date == today:
                        today_count += 1

                    for i in range(7):
                        if email_date == today - timedelta(days=i):
                            weekly_data[6 - i] += 1

                except Exception:
                    continue

        total = processed + failed
        success_rate = round((processed / total) * 100, 1) if total > 0 else 0

        return {
            "statusCode": 200,
            "body": json.dumps({
                "today": today_count,
                "processed": processed,
                "failed": failed,
                "auto_replies": auto_replies,
                "success_rate": success_rate,
                "weekly_data": weekly_data,
                "keyword_distribution": dict(keyword_distribution),
                "records": items
            }, default=str)
        }

    except Exception as e:
        print("Error:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }