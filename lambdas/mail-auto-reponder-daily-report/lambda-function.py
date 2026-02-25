import boto3
import os
import pandas as pd
from datetime import datetime, timedelta
import tempfile
import base64

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.mime.text import MIMEText
import json

dynamodb = boto3.resource('dynamodb')
secrets = boto3.client('secretsmanager')

TABLE_NAME = os.environ['TABLE_NAME']
SECRET_NAME = os.environ['SECRET_NAME']
SUPERVISOR_EMAIL = os.environ['SUPERVISOR_EMAIL']


def get_secret():
    response = secrets.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])


def lambda_handler(event, context):

    table = dynamodb.Table(TABLE_NAME)

    # Get today's date range
    today = datetime.utcnow().date()
    start_time = datetime(today.year, today.month, today.day)
    end_time = start_time + timedelta(days=1)

    # Scan DynamoDB (simple version)
    response = table.scan()
    items = response.get('Items', [])

    if not items:
        print("No data found.")
        return

    # Convert to DataFrame
    df = pd.DataFrame(items)

    # Create CSV file in temp directory
    file_path = "/tmp/daily_report.csv"
    df.to_csv(file_path, index=False)

    print("CSV file created.")

    # Send Email with attachment
    secret = get_secret()

    creds = Credentials(
        None,
        refresh_token=secret['refresh_token'],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=secret['gmail_client_id'],
        client_secret=secret['gmail_client_secret']
    )

    service = build('gmail', 'v1', credentials=creds)

    message = MIMEMultipart()
    message['To'] = SUPERVISOR_EMAIL
    message['Subject'] = "Daily Auto Responder Report"

    body = "Please find attached daily report."
    message.attach(MIMEText(body, 'plain'))

    # Attach CSV
    with open(file_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename=daily_report.csv"
        )
        message.attach(part)

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    service.users().messages().send(
        userId="me",
        body={'raw': raw_message}
    ).execute()

    print("Daily report sent successfully.")
