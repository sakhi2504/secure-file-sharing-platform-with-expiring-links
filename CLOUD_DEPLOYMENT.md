# Cloud Deployment Checklist

This project supports AWS S3 for file storage, MongoDB Atlas for share metadata, and Streamlit Community Cloud for hosting. The application code is ready to use these services; you must create the cloud resources and add their settings.

## 1. Create the AWS storage

1. In AWS, create an S3 bucket in a region you choose.
2. Keep **Block all public access** enabled.
3. Create an IAM identity for the app with permissions limited to this bucket:
   - `s3:ListBucket` on `arn:aws:s3:::YOUR_BUCKET`
   - `s3:PutObject` and `s3:GetObject` on `arn:aws:s3:::YOUR_BUCKET/*`
4. Save the bucket name, region, and access credentials securely. The app needs bucket-level listing for its connection check and object read/write permissions. See the [AWS S3 IAM example](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_s3_rw-bucket.html).

## 2. Create MongoDB Atlas storage

1. Create an Atlas project and database cluster.
2. Create a database user for this app with access to the project database.
3. Add the app host to Atlas Network Access.
4. In the cluster's **Connect → Drivers** instructions, copy the Python connection string and replace its username/password placeholders. URL-encode reserved characters in the password if needed. See [MongoDB's connection-string guide](https://www.mongodb.com/docs/manual/reference/connection-string/).

## 3. Put the project in GitHub

Streamlit Community Cloud deploys from a GitHub repository. Create a private repository, then upload these project files:
- `app.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `README.md`

Do not upload `.env`, local `data/` or `uploads/` folders, AWS keys, or Atlas credentials. They are ignored by `.gitignore`.

## 4. Deploy the Streamlit app

1. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and choose **Create app**.
2. Select the repository and use `app.py` as the app file.
3. In **Advanced settings → Secrets**, add settings in TOML format:

```toml
UPLOAD_PASSWORD = "choose-a-long-owner-password"
APP_BASE_URL = "https://your-app-name.streamlit.app"
AWS_REGION = "ap-south-1"
S3_BUCKET = "your-bucket-name"
AWS_ACCESS_KEY_ID = "your-restricted-access-key"
AWS_SECRET_ACCESS_KEY = "your-secret-key"
MONGODB_URI = "mongodb+srv://..."
MONGODB_DB = "secure_file_sharing"
```

Keep these secrets in Streamlit's settings, never in GitHub or chat. Streamlit documents this deployment and secret flow in its [Community Cloud deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [secrets guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

If you need the app URL before setting `APP_BASE_URL`, deploy once, copy the URL, then set the secret and save/reboot the app.

## 5. Confirm connections

Open the deployed app, expand **Cloud connection setup**, and select **Check cloud connections**. Both S3 and MongoDB should report that the connection is working. Then upload a small sample file and open its link from another device.

S3 objects remain stored after a link expires. Set an S3 Lifecycle rule to clean them up after your chosen retention period.
