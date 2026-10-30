# Secure File Sharing Platform with Expiring Links

A Python + Streamlit mini project for uploading files and creating temporary download links. Recipients can use an optional password to access a shared file.

## Run locally

1. Install Python 3.10 or newer.
2. Open PowerShell in this project folder.
3. Create your settings file: `Copy-Item .env.example .env`.
4. Open `.env` and set `UPLOAD_PASSWORD`.
5. Install dependencies with `pip install -r requirements.txt`.
6. Start the app with `streamlit run app.py`, then open http://localhost:8501.

With S3_BUCKET and MONGODB_URI left blank, this runs in local demo mode. Files are stored in `uploads/` and metadata in `data/`. Use the “Cloud connection setup” expander in the app to check configured connections.

## Connect AWS S3 and MongoDB Atlas

1. Create a private S3 bucket and keep Block Public Access enabled.
2. Create a restricted IAM identity for this app. It needs `s3:ListBucket` on the bucket ARN for the connection check, and `s3:PutObject` and `s3:GetObject` on that bucket's object ARN. Do not grant public access.
3. Set `AWS_REGION` and `S3_BUCKET` in `.env`. Locally, use your normal AWS credential profile or set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as environment variables. For deployment, use the hosting platform's secret store. Never commit credentials.
4. Create an Atlas database user and copy the application connection string from Atlas. Set it as `MONGODB_URI`; set `MONGODB_DB` if desired. Atlas must allow network connections from the app host, and the database user must have access to this database.
5. Set `APP_BASE_URL` to the app's public HTTPS URL after deployment. Restart the app and use “Check cloud connections”.

For Streamlit Community Cloud, deploy the app from a GitHub repository and add the values as app secrets in its settings. Keep `.env` and `.streamlit/secrets.toml` out of GitHub. Streamlit reads the same setting names from its secrets store.

The app stores files privately in S3 and issues presigned download URLs for at most 10 minutes after checking the share token and optional password. MongoDB's TTL index removes expired metadata asynchronously; configure an S3 Lifecycle rule to remove expired file objects because expiring a link does not delete the S3 object.

## Cloud architecture

Browser → Streamlit app → private S3 bucket  
                     ↘ MongoDB share metadata

This is a class project prototype. Add user accounts and ownership, audit logs, malware scanning, and reliable object cleanup before using it for sensitive files.

