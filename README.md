# 🔗 Shortr — Serverless URL Shortener

> A production-style URL shortener built on AWS. Enter a long URL → get a short redirect link with persistent click tracking. 100% serverless, zero servers to manage.

🔗 **Live demo:** http://urlshort-site-8472.s3-website-ap-southeast-1.amazonaws.com

---

## 📸 Preview

Add a `screenshot.png` to `docs/` and reference it here.

---

## 🏗️ Architecture

```
┌─────────────┐
│   Visitor   │
└──────┬──────┘
       │
       ├─────► GET / (static site)
       │        ▼
       │   ┌─────────────────┐
       │   │  S3 (frontend)  │
       │   └─────────────────┘
       │
       ├─────► POST /shorten  (create short URL)
       │        ▼
       │   ┌─────────────────┐    ┌─────────────────┐
       │   │  API Gateway    │───►│  Lambda         │
       │   │  (HTTP API v2)  │    │  (Python 3.12)  │
       │   └─────────────────┘    └────────┬────────┘
       │                                    ▼
       │                           ┌─────────────────┐
       │                           │  DynamoDB       │
       │                           │  (short→long)   │
       │                           └─────────────────┘
       │
       └─────► GET /{short_id}  (redirect)
                ▼
          (same Lambda returns 302 + Location header)
```

| Component | AWS Service | Role |
|---|---|---|
| Static frontend | **S3** | Serves the HTML form |
| HTTP API | **API Gateway (v2)** | Two routes: `POST /shorten`, `GET /{short_id}` |
| Compute | **Lambda (Python 3.12)** | Short ID generation, DynamoDB CRUD, HTTP 302 redirect |
| Database | **DynamoDB** | `short_id` → `long_url` mapping + atomic click counter |
| Permissions | **IAM** | Lambda execution role with least-privilege DynamoDB access |

---

## ⚡ Features

- 🔗 **Short IDs** — 6-char alphanumeric (base62), ~56 billion possibilities
- 🛡️ **Collision-safe writes** — DynamoDB `ConditionExpression="attribute_not_exists(short_id)"` auto-retries on rare collision
- 📊 **Atomic click counting** — DynamoDB `ADD clicks :one` won't lose counts under concurrent clicks
- ✅ **URL validation** — only `http://` and `https://` accepted
- 📋 **One-click copy** — short URL copies to clipboard
- 🎨 **Clean UI** — dark theme, animated gradient logo, responsive
- 🌐 **CORS-enabled** — frontend hostable anywhere
- 🤖 **Fully serverless** — zero servers, scales from 0 to millions
- 💾 **~$0 at low scale** — DynamoDB Free Tier (25 GB forever), Lambda Free Tier (1M requests/month forever)

---

## 📁 Project Structure

```
url-shortener/
├── README.md
├── .gitignore
├── frontend/
│   └── index.html           # Vanilla HTML/CSS/JS form
├── lambda/
│   └── lambda_function.py   # Shorten + redirect handler
├── iam/
│   ├── lambda-trust.json    # Trust policy for Lambda service
│   ├── dynamo-policy.json   # Least-privilege DynamoDB access
│   └── urlshort-bucket-policy.json  # Public-read for frontend bucket
└── docs/
```

---

## 🧠 How It Works

### Creating a short URL (`POST /shorten`)

```json
Request body: { "long_url": "https://example.com/very/long/path" }
```

1. Lambda validates the URL format
2. Generates a 6-char random base62 ID (e.g., `OxqRtt`)
3. Attempts `PutItem` with `ConditionExpression` — if the ID exists, retry up to 5 times
4. Returns `{ "short_id": "OxqRtt", "long_url": "..." }`

### Visiting a short URL (`GET /{short_id}`)

1. API Gateway's path parameter extracts the ID
2. Lambda looks up the long URL in DynamoDB
3. Atomically increments the click counter
4. Returns HTTP 302 with `Location: <long_url>` header
5. Browser auto-follows the redirect

---

## 🚀 Deploy It Yourself

### Prerequisites
- AWS account with CLI configured (`aws configure`)
- Region: `ap-southeast-1` (adjust as needed)
- Python 3.12

### 1. DynamoDB table

```bash
aws dynamodb create-table \
  --table-name urlshort-links \
  --attribute-definitions AttributeName=short_id,AttributeType=S \
  --key-schema AttributeName=short_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-southeast-1
```

### 2. IAM role for Lambda

```bash
aws iam create-role --role-name urlshort-role \
  --assume-role-policy-document file://iam/lambda-trust.json

aws iam attach-role-policy --role-name urlshort-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam put-role-policy --role-name urlshort-role \
  --policy-name DynamoDBAccess \
  --policy-document file://iam/dynamo-policy.json
```

> ⚠️ Update account ID and region in `iam/dynamo-policy.json` first.

### 3. Package and deploy the Lambda

```bash
cd lambda
zip -r ../function.zip lambda_function.py
cd ..

aws lambda create-function --function-name urlshort-handler \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/urlshort-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip \
  --region ap-southeast-1
```

### 4. API Gateway with two routes

```bash
# Create the API with CORS
API_ID=$(aws apigatewayv2 create-api \
  --name urlshort-api \
  --protocol-type HTTP \
  --cors-configuration AllowOrigins="*",AllowMethods="GET,POST,OPTIONS",AllowHeaders="Content-Type" \
  --query "ApiId" --output text \
  --region ap-southeast-1)

# Create Lambda integration
INT_ID=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type AWS_PROXY \
  --integration-uri arn:aws:lambda:ap-southeast-1:YOUR_ACCOUNT:function:urlshort-handler \
  --payload-format-version 2.0 \
  --query "IntegrationId" --output text \
  --region ap-southeast-1)

# Routes
aws apigatewayv2 create-route --api-id $API_ID \
  --route-key "POST /shorten" --target "integrations/$INT_ID" \
  --region ap-southeast-1

aws apigatewayv2 create-route --api-id $API_ID \
  --route-key "GET /{short_id}" --target "integrations/$INT_ID" \
  --region ap-southeast-1

# Default stage
aws apigatewayv2 create-stage --api-id $API_ID \
  --stage-name '$default' --auto-deploy \
  --region ap-southeast-1

# Grant API Gateway permission to invoke Lambda
aws lambda add-permission --function-name urlshort-handler \
  --statement-id APIGatewayInvoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:ap-southeast-1:YOUR_ACCOUNT:$API_ID/*/*" \
  --region ap-southeast-1
```

### 5. Deploy the frontend

Edit `frontend/index.html` and replace `API_BASE` with your API Gateway URL, then:

```bash
aws s3 mb s3://your-bucket-name --region ap-southeast-1
aws s3 website s3://your-bucket-name/ --index-document index.html
# apply iam/urlshort-bucket-policy.json (update bucket name in it)
aws s3api put-bucket-policy --bucket your-bucket-name \
  --policy file://iam/urlshort-bucket-policy.json
aws s3 cp frontend/index.html s3://your-bucket-name/
```

---

## 🧠 Key Design Decisions

**Why one Lambda for two routes?** Avoids function sprawl for related logic. Shared code (DynamoDB client, response helpers) stays DRY. Routing is handled by checking `event.requestContext.http.method` and `event.requestContext.http.path`.

**Why DynamoDB over RDS?** URL lookup is a pure key-value pattern — exactly what DynamoDB is designed for. Single-digit ms latency, scales infinitely, no instance management.

**Why `ConditionExpression="attribute_not_exists(short_id)"`?** Prevents accidental overwrite if two concurrent requests happen to generate the same random ID (astronomically rare at 56B combinations but handled correctly).

**Why `ADD clicks :one` instead of fetching + incrementing?** Atomic server-side operation. No race condition under concurrent clicks. Faster (one round-trip).

**Why 302 redirect instead of HTML meta refresh?** HTTP-level redirects are faster, SEO-friendly, and work for CLI tools (`curl`, `wget`).

**Why least-privilege IAM policy?** The Lambda only needs `PutItem`, `GetItem`, and `UpdateItem` on one specific table. Not `AmazonDynamoDBFullAccess`. If the Lambda is ever compromised, blast radius is limited.

---

## 🛠️ Tech Stack

**Languages:** Python 3.12 · HTML5 · CSS3 · JavaScript (ES6+ async/await)
**AWS Services:** S3 · API Gateway (HTTP API v2) · Lambda · DynamoDB · IAM · CloudWatch Logs
**Tools:** AWS CLI · PowerShell · boto3

---

## 📊 What I Learned

- API Gateway HTTP API v2 routing (vs REST API)
- DynamoDB conditional writes for collision handling
- Atomic counter operations in DynamoDB
- Lambda proxy integration response format (statusCode + headers + body)
- HTTP 302 redirects from Lambda
- CORS configuration across API Gateway and Lambda response headers
- Browser clipboard API

---

## 🔮 Future Enhancements

- [ ] Custom aliases (`/zetrax` instead of random `/OxqRtt`)
- [ ] Click analytics dashboard (hourly/daily breakdown)
- [ ] QR code generation for each short URL
- [ ] Expiration dates / self-destructing links
- [ ] User authentication via Cognito
- [ ] CloudFront in front for HTTPS + global edge caching
- [ ] Custom domain via Route 53 (`https://zt.lo/abc`)
- [ ] Terraform / CDK for infrastructure as code

---

## 📜 License

MIT. Use freely.

---

*Built as a hands-on AWS serverless project.*
