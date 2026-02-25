import uuid
import datetime
import os
import boto3
import base64
import json
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# AWS Clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
secrets = boto3.client('secretsmanager')

TABLE_NAME = os.environ['TABLE_NAME']
BUCKET_NAME = os.environ['BUCKET_NAME']
SECRET_NAME = os.environ['SECRET_NAME']

KEYWORDS = ["invoice", "payment", "bill"]


def get_secret():
    response = secrets.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])


def extract_email(sender_raw):
    if not sender_raw:
        return "unknown"
    match = re.search(r'<(.+?)>', sender_raw)
    return match.group(1) if match else sender_raw


def lambda_handler(event, context):

    print("Lambda started")

    try:
        secret = get_secret()

        creds = Credentials(
            None,
            refresh_token=secret['refresh_token'],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=secret['gmail_client_id'],
            client_secret=secret['gmail_client_secret']
        )

        service = build('gmail', 'v1', credentials=creds)

        # Get all unread emails (with pagination)
        messages = []
        next_page_token = None

        while True:
            response = service.users().messages().list(
                userId='me',
                q='is:unread',
                pageToken=next_page_token
            ).execute()

            messages.extend(response.get('messages', []))
            next_page_token = response.get('nextPageToken')

            if not next_page_token:
                break

        if not messages:
            print("No unread emails found.")
            return

        table = dynamodb.Table(TABLE_NAME)

        for msg in messages:

            start_time = datetime.datetime.utcnow()

            transaction_id = str(uuid.uuid4())
            timestamp = start_time.strftime("%Y-%m-%d %H:%M:%S")

            msg_id = msg['id']

            # Default values
            result = "NO"
            remark = "Keyword not found"
            auto_reply = False
            matched_keyword = None
            status = "FAILED"
            sender = "unknown"
            subject = ""

            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg_id
                ).execute()

                headers = message['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "")
                sender_raw = next((h['value'] for h in headers if h['name'] == 'From'), "")
                sender = extract_email(sender_raw)

                # Find matched keyword
                matched_keyword = next(
                    (k for k in KEYWORDS if subject and k in subject.lower()),
                    None
                )

                if matched_keyword:

                    template = s3.get_object(
                        Bucket=BUCKET_NAME,
                        Key="invoice_template.html"
                    )['Body'].read().decode()

                    raw_message = base64.urlsafe_b64encode(
                        f"To: {sender}\n"
                        f"Subject: Re: {subject}\n"
                        f"Content-Type: text/html\n\n"
                        f"{template}".encode()
                    ).decode()

                    service.users().messages().send(
                        userId="me",
                        body={'raw': raw_message}
                    ).execute()

                    auto_reply = True
                    result = "YES"
                    status = "SUCCESS"
                    remark = "Auto responder sent"

                # Mark email as read
                service.users().messages().modify(
                    userId='me',
                    id=msg_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()

            except Exception as process_error:
                remark = str(process_error)
                status = "FAILED"
                auto_reply = False

            # Calculate processing time
            end_time = datetime.datetime.utcnow()
            processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Store in DynamoDB (ALWAYS STORE)
            try:
                table.put_item(
                    Item={
                        'transaction_id': transaction_id,
                        'timestamp': timestamp,
                        'sender_email': sender,
                        'subject': subject,
                        'auto_reply': auto_reply,
                        'keyword': matched_keyword if matched_keyword else "none",
                        'status': status,
                        'result': result,
                        'remark': remark,
                        'processing_time_ms': processing_time_ms
                    }
                )

                print(f"Stored in DB: {transaction_id}")

            except Exception as ddb_error:
                print("DynamoDB Error:", str(ddb_error))

        print("Lambda completed successfully")

    except Exception as e:
        print("Fatal Error:", str(e))
        raise e