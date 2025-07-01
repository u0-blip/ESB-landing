# SCRIPT
SCRIPT_NAME=${0##*/}
ENVIRONMENT=$1

if [[ -z "$SCRIPT_NAME" ]]; then
  echo "Usage: build-and-deploy_sh.sh environment"
  echo "Server Names: live OR test OR local"
  exit 1
fi

# convert to lower case
ENVIRONMENT=$(echo $ENVIRONMENT | tr '[A-Z]' '[a-z]')

# check if the environment argument is live or test
if [[ $ENVIRONMENT != "live" && $ENVIRONMENT != "test" && $ENVIRONMENT != "local" ]]; then
  echo "Usage: ${SCRIPT_NAME} %ENV-NAME%"
  echo "ENV-NAME: live OR test OR local"
  exit 1
fi

ENV_FILE=.env.${ENVIRONMENT}
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file $ENV_FILE does NOT exist"
  exit 1
fi

echo "Check environment"
if [ ${ENVIRONMENT} = "live" ]; then
  S3_BUCKET_NAME="elitesportsbets.com"
  DISTRIBUTION_ID="E2S8BECPMTO0U5"
else
  S3_BUCKET_NAME="test.elitesportsbets.com"
  DISTRIBUTION_ID="E1POGTX3CJWLXZ"
fi

echo "Reading ${ENV_FILE}"
set -a && source ${ENV_FILE} && set +a

echo "Resetting dist directory"
rm -rf dist
mkdir -p dist

echo "Synching resources"
cp *.html dist
cp -R js css assets dist

echo "Replacing Variables"
# alternative: find dist -type f -name '*.html' -exec sed -i "s/%S3_BUCKET_NAME%/${S3_BUCKET_NAME}/g" {} +
# find dist -type f -name '*.html' | xargs sed -i "s/%S3_BUCKET_NAME%/${S3_BUCKET_NAME}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%SIGNIN_REDIRECT_URL%/${SIGNIN_REDIRECT_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%SIGNUP_REDIRECT_URL%/${SIGNUP_REDIRECT_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%SIGNIN_COGNITO_URL%/${SIGNIN_COGNITO_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%SIGNUP_COGNITO_URL%/${SIGNUP_COGNITO_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%COGNITO_APP_CLIENT_ID%/${COGNITO_APP_CLIENT_ID}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%SCORECARD_REDIRECT_URL%/${SCORECARD_REDIRECT_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%PICKS_REDIRECT_URL%/${PICKS_REDIRECT_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%MAIL_API_URL%/${MAIL_API_URL}/g"
find dist -type f -name '*.html' | xargs sed -i "s/%GRAPHQL_API_URL%/${GRAPHQL_API_URL}/g"

echo "Build Success"

if [[ $ENVIRONMENT == "local" ]]; then
  exit 0
fi

echo "Deploying to ${ENVIRONMENT} environment"

echo "Deploying via AWS CLI"
aws s3 sync --delete ./dist s3://"${S3_BUCKET_NAME}" --acl public-read --profile esb

echo "Creating CloudFront invalidation"
aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID}" --paths /\* --profile esb

echo "Deploy Success"
